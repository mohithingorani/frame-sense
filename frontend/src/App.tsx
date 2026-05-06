import { useEffect, useMemo, useRef, useState } from 'react'

type ROI = {
  id: number
  timestamp: string
  x: number
  y: number
  width: number
  height: number
}

type FrameOutput = {
  image_base64: string
  roi?: ROI
  note?: string
}

const API_WS = import.meta.env.VITE_API_WS || 'ws://localhost:8000'

function App() {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const inputSocketRef = useRef<WebSocket | null>(null)
  const outputSocketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number>(Date.now())
  const framesSentRef = useRef<number>(0)

  const [status, setStatus] = useState('connecting')
  const [processedFrame, setProcessedFrame] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [roi, setRoi] = useState<ROI | null>(null)
  const [resolution, setResolution] = useState('640 x 480')
  const [fps, setFps] = useState(0)

  useEffect(() => {
    let mediaStream: MediaStream | undefined

    const start = async () => {
      mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
        videoRef.current.onloadedmetadata = () => {
          videoRef.current?.play()
          setStreaming(true)
        }
        videoRef.current.onplay = () => setStreaming(true)
        videoRef.current.onerror = () => setStatus('camera_error')
      }

      const inputWs = new WebSocket(`${API_WS}/stream/input`)
      const outputWs = new WebSocket(`${API_WS}/stream/output`)
      inputSocketRef.current = inputWs
      outputSocketRef.current = outputWs

      outputWs.onopen = () => {
        outputWs.send('ready')
      }

      outputWs.onmessage = (event: MessageEvent<string>) => {
        const data: FrameOutput = JSON.parse(event.data)
        if (data.image_base64) {
          setProcessedFrame(`data:image/jpeg;base64,${data.image_base64}`)
        }
        if (data.roi) {
          setRoi(data.roi)
          setStatus('face_detected')
        } else if (data.note === 'no_face') {
          setStatus('no_face')
          setRoi(null)
        }
      }

      const sendFrame = () => {
        const video = videoRef.current
        const canvas = canvasRef.current
        const ws = inputSocketRef.current

        if (!video || !canvas || !ws || ws.readyState !== WebSocket.OPEN) {
          return
        }

        const width = video.videoWidth || 640
        const height = video.videoHeight || 480
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          return
        }

        canvas.width = width
        canvas.height = height
        setResolution(`${width} x ${height}`)

        ctx.drawImage(video, 0, 0, width, height)
        canvas.toBlob((blob) => {
          if (blob && ws.readyState === WebSocket.OPEN) {
            ws.send(blob)
            framesSentRef.current += 1
            const elapsed = (Date.now() - startedAtRef.current) / 1000
            if (elapsed > 0) {
              setFps(Math.round(framesSentRef.current / elapsed))
            }
          }
        }, 'image/jpeg', 0.75)
      }

      inputWs.onopen = () => {
        setStatus('connected')
        timerRef.current = window.setInterval(sendFrame, 100)
      }

      inputWs.onclose = () => setStatus('input_disconnected')
      outputWs.onclose = () => setStatus('output_disconnected')
    }

    start().catch(() => setStatus('camera_error'))

    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current)
      }
      inputSocketRef.current?.close()
      outputSocketRef.current?.close()
      mediaStream?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  const isConnected = useMemo(
    () => !['camera_error', 'input_disconnected', 'output_disconnected'].includes(status),
    [status],
  )

  const detectionText = status === 'face_detected' ? 'Face Detected' : status === 'no_face' ? 'No Face' : 'Detecting...'

  return (
    <div className="min-h-screen bg-slate-100 p-6">
      <div className="mx-auto w-full max-w-6xl rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
          <div>
            <h1 className="text-2xl font-semibold">Face Detection</h1>
            <p className="text-sm text-slate-500">Real-time face detection and tracking</p>
          </div>
          <div className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium">
            <span className={`mr-2 inline-block h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-red-500'}`} />
            {isConnected ? 'Connected' : 'Disconnected'}
            {streaming && ' • Streaming'}
          </div>
        </header>

        <main className="grid grid-cols-1 gap-4 p-6 lg:grid-cols-3">
          <section className="lg:col-span-2">
              <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
                <span className="absolute left-4 top-4 z-10 rounded-md bg-white/90 px-3 py-1 text-xs font-semibold">LIVE</span>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className={`h-[430px] w-full object-cover ${processedFrame ? 'opacity-50' : 'opacity-100'}`}
                />
                {processedFrame && (
                  <img
                    src={processedFrame}
                    alt="Processed stream"
                    className="absolute inset-0 h-full w-full object-cover"
                  />
                )}
                <canvas ref={canvasRef} className="hidden" />
              </div>
            </section>

          <aside className="rounded-xl border border-slate-200 p-5">
            <h2 className="mb-4 text-lg font-semibold">Detection</h2>
            <div className="mb-4 rounded-lg border border-slate-100 bg-slate-50 p-3">
              <p className="text-sm font-medium text-emerald-600">{detectionText}</p>
            </div>
            <div className="space-y-2 text-sm text-slate-600">
              <p>Time: {roi ? new Date(roi.timestamp).toLocaleString() : '-'}</p>
              <p>Bounding Box (ROI)</p>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2 text-center text-sm">
              <div><p className="text-slate-400">X</p><p className="font-semibold">{roi?.x ?? '-'}</p></div>
              <div><p className="text-slate-400">Y</p><p className="font-semibold">{roi?.y ?? '-'}</p></div>
              <div><p className="text-slate-400">Width</p><p className="font-semibold">{roi?.width ?? '-'}</p></div>
              <div><p className="text-slate-400">Height</p><p className="font-semibold">{roi?.height ?? '-'}</p></div>
            </div>
          </aside>
        </main>

        <footer className="flex flex-wrap items-center justify-between border-t border-slate-200 px-6 py-4 text-sm">
          <div className="flex gap-3">
            <button className="rounded-lg bg-slate-900 px-6 py-2 font-medium text-white">Stop Stream</button>
            <button className="rounded-lg border border-slate-300 px-6 py-2 font-medium text-slate-700">Switch Camera</button>
          </div>
          <div className="mt-3 flex gap-8 text-slate-600 md:mt-0">
            <p>FPS <span className="font-semibold text-slate-900">{fps}</span></p>
            <p>Resolution <span className="font-semibold text-slate-900">{resolution}</span></p>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default App
