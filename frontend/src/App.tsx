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
  error?: string
}

const API_WS = import.meta.env.VITE_API_WS || 'ws://localhost:8000'

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY_MS = 2000
const RECONNECT_BACKOFF_MS = 1000

function App() {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const inputSocketRef = useRef<WebSocket | null>(null)
  const outputSocketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number>(Date.now())
  const framesSentRef = useRef<number>(0)
  const reconnectAttemptsRef = useRef<number>(0)
  const isStreamActiveRef = useRef<boolean>(true)
  const currentDeviceIdRef = useRef<string | null>(null)

  const [status, setStatus] = useState<'connecting' | 'connected' | 'face_detected' | 'no_face' | 'camera_error' | 'processing_error' | 'reconnecting' | 'stopped'>('connecting')
  const [processedFrame, setProcessedFrame] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [roi, setRoi] = useState<ROI | null>(null)
  const [resolution, setResolution] = useState('640 x 480')
  const [fps, setFps] = useState(0)
  const [availableCameras, setAvailableCameras] = useState<{ id: string; label: string }[]>([])
  const [selectedCamera, setSelectedCamera] = useState<string>('')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)

  const cleanupConnections = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (inputSocketRef.current) {
      inputSocketRef.current.close()
      inputSocketRef.current = null
    }
    if (outputSocketRef.current) {
      outputSocketRef.current.close()
      outputSocketRef.current = null
    }
  }

  const stopStream = () => {
    isStreamActiveRef.current = false
    cleanupConnections()
    if (videoRef.current?.srcObject) {
      const tracks = (videoRef.current.srcObject as MediaStream).getTracks()
      tracks.forEach((track) => track.stop())
      videoRef.current.srcObject = null
    }
    setStreaming(false)
    setStatus('stopped')
    setIsLoading(false)
    startedAtRef.current = Date.now()
    framesSentRef.current = 0
    setFps(0)
  }

  const loadCameras = async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const videoDevices = devices.filter((d) => d.kind === 'videoinput')
      setAvailableCameras(videoDevices.map((d) => ({ id: d.deviceId, label: d.label || `Camera ${d.deviceId.slice(0, 8)}` })))
      
      if (videoDevices.length > 0 && !selectedCamera) {
        setSelectedCamera(videoDevices[0].deviceId)
      }
    } catch (err) {
      console.error('Failed to enumerate devices:', err)
      setErrorMessage('Could not access camera devices')
    }
  }

  const switchCamera = async (deviceId: string) => {
    stopStream()
    setSelectedCamera(deviceId)
    currentDeviceIdRef.current = deviceId
    startStream(deviceId)
  }

  const startStream = async (deviceId?: string) => {
    isStreamActiveRef.current = true
    setErrorMessage('')
    setIsLoading(true)
    let mediaStream: MediaStream | undefined

    const constraints: MediaStreamConstraints = {
      video: deviceId ? { deviceId: { exact: deviceId } } : true,
      audio: false,
    }

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
      currentDeviceIdRef.current = mediaStream.getVideoTracks()[0]?.getSettings().deviceId || null
      setSelectedCamera(currentDeviceIdRef.current || '')

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
        videoRef.current.onloadedmetadata = () => {
          videoRef.current?.play()
        }
        videoRef.current.onplay = () => {
          setStreaming(true)
          setIsLoading(false)
        }
        videoRef.current.onerror = () => {
          setStatus('camera_error')
          setErrorMessage('Camera error occurred')
          setIsLoading(false)
        }
      }
    } catch (err) {
      console.error('Camera access error:', err)
      setStatus('camera_error')
      setIsLoading(false)
      
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError') {
          setErrorMessage('Camera access denied. Please allow camera permissions.')
        } else if (err.name === 'NotFoundError') {
          setErrorMessage('No camera found on this device')
        } else {
          setErrorMessage(`Camera error: ${err.message}`)
        }
      }
      return
    }

    const connectWebSockets = () => {
      const inputWs = new WebSocket(`${API_WS}/stream/input`)
      const outputWs = new WebSocket(`${API_WS}/stream/output`)
      inputSocketRef.current = inputWs
      outputSocketRef.current = outputWs

      outputWs.onopen = () => {
        reconnectAttemptsRef.current = 0
        outputWs.send('ready')
      }

      outputWs.onmessage = (event: MessageEvent<string>) => {
        try {
          const data: FrameOutput = JSON.parse(event.data)
          
          if (data.error) {
            setStatus('processing_error')
            setErrorMessage(data.error)
            return
          }
          
          if (data.image_base64) {
            setProcessedFrame(`data:image/jpeg;base64,${data.image_base64}`)
          }
          if (data.roi) {
            setRoi(data.roi)
            setStatus('face_detected')
            setErrorMessage('')
          } else if (data.note === 'no_face') {
            setStatus('no_face')
            setRoi(null)
          } else if (data.note === 'processing_error') {
            setStatus('processing_error')
            setErrorMessage('Server processing error')
          } else if (data.note === 'frame_too_large') {
            setErrorMessage('Frame too large for server')
          }
        } catch (err) {
          console.error('Failed to parse message:', err)
        }
      }

      outputWs.onerror = () => {
        if (isStreamActiveRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptsRef.current)
          reconnectAttemptsRef.current++
          setStatus('reconnecting')
          setTimeout(connectWebSockets, delay)
        }
      }

      outputWs.onclose = (event) => {
        if (isStreamActiveRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptsRef.current)
          reconnectAttemptsRef.current++
          setStatus('reconnecting')
          setTimeout(connectWebSockets, delay)
        } else if (isStreamActiveRef.current) {
          setStatus('camera_error')
          setErrorMessage('Connection failed after multiple attempts')
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

      inputWs.onerror = () => {
        if (isStreamActiveRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptsRef.current)
          reconnectAttemptsRef.current++
          setStatus('reconnecting')
          setTimeout(connectWebSockets, delay)
        }
      }

      inputWs.onclose = () => {
        if (isStreamActiveRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptsRef.current)
          reconnectAttemptsRef.current++
          setStatus('reconnecting')
          setTimeout(connectWebSockets, delay)
        }
      }
    }

    connectWebSockets()

    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current)
      }
      inputSocketRef.current?.close()
      outputSocketRef.current?.close()
      mediaStream?.getTracks().forEach((track) => track.stop())
    }
  }

  useEffect(() => {
    loadCameras()
    startStream()
    return () => {
      stopStream()
    }
  }, [])

  const isConnected = useMemo(
    () => status === 'connected' || status === 'face_detected' || status === 'no_face' || status === 'reconnecting',
    [status],
  )

  const detectionText = useMemo(() => {
    switch (status) {
      case 'face_detected': return 'Face Detected'
      case 'no_face': return 'No Face'
      case 'camera_error': return 'Camera Error'
      case 'processing_error': return 'Processing Error'
      case 'reconnecting': return 'Reconnecting...'
      case 'connecting': return 'Connecting...'
      case 'stopped': return 'Stopped'
      default: return 'Detecting...'
    }
  }, [status])

  const isLoadingCamera = status === 'connecting'
  
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
            {status === 'reconnecting' ? 'Reconnecting' : isConnected ? 'Connected' : 'Disconnected'}
            {streaming && ' • Streaming'}
          </div>
        </header>

        <main className="grid grid-cols-1 gap-4 p-6 lg:grid-cols-3">
          <section className="lg:col-span-2">
            <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
              <span className="absolute left-4 top-4 z-10 rounded-md bg-white/90 px-3 py-1 text-xs font-semibold">LIVE</span>
              
              {isLoadingCamera && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
                  <div className="flex flex-col items-center gap-2">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <p className="text-sm text-slate-400">Initializing camera...</p>
                  </div>
                </div>
              )}
              
              {status === 'camera_error' && !isLoadingCamera && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
                  <div className="flex flex-col items-center gap-2 text-center">
                    <svg className="h-10 w-10 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <p className="text-sm text-red-400">{errorMessage || 'Camera error'}</p>
                  </div>
                </div>
              )}
              
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                className={`h-[430px] w-full object-cover ${processedFrame ? 'opacity-50' : 'opacity-100'} ${isLoadingCamera || status === 'camera_error' ? 'hidden' : ''}`}
              />
              {processedFrame && status !== 'camera_error' && !isLoadingCamera && (
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
            <div className={`mb-4 rounded-lg border p-3 ${
              status === 'face_detected' ? 'bg-emerald-50 border-emerald-200' :
              status === 'no_face' ? 'bg-slate-50 border-slate-200' :
              status === 'camera_error' || status === 'processing_error' ? 'bg-red-50 border-red-200' :
              'bg-slate-50 border-slate-200'
            }`}>
              <p className={`text-sm font-medium ${
                status === 'face_detected' ? 'text-emerald-600' :
                status === 'no_face' ? 'text-slate-600' :
                status === 'camera_error' || status === 'processing_error' ? 'text-red-600' :
                'text-slate-600'
              }`}>{detectionText}</p>
              {errorMessage && status !== 'face_detected' && status !== 'no_face' && (
                <p className="mt-1 text-xs text-red-500">{errorMessage}</p>
              )}
            </div>
            
            <div className="mb-4">
              <label className="mb-2 block text-sm font-medium text-slate-600">Camera</label>
              <select
                value={selectedCamera}
                onChange={(e) => switchCamera(e.target.value)}
                disabled={availableCameras.length <= 1}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              >
                {availableCameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>
                    {camera.label}
                  </option>
                ))}
              </select>
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
            <button
              onClick={stopStream}
              className="rounded-lg bg-slate-900 px-6 py-2 font-medium text-white hover:bg-slate-800"
            >
              Stop Stream
            </button>
            <button
              onClick={() => loadCameras().then(() => selectedCamera && switchCamera(selectedCamera))}
              className="rounded-lg border border-slate-300 px-6 py-2 font-medium text-slate-700 hover:bg-slate-50"
            >
              Refresh Camera
            </button>
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