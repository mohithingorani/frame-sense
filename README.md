# Face Sense

Real-time face detection and tracking application with WebSocket streaming.

## Architecture

- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI (Python) with PostgreSQL
- **Face Detection**: MediaPipe

## Quick Start

### Using Docker Compose

```bash
docker compose up --build
```

Access the application at http://localhost:5173

### Manual Setup

#### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

### Backend

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://postgres:postgres@db:5432/facestream | Database connection string |
| MAX_FRAME_BYTES | 2097152 | Max frame size (bytes) |
| MAX_WIDTH | 1920 | Max video width |
| MAX_HEIGHT | 1080 | Max video height |
| MAX_FPS_PER_CLIENT | 12 | Rate limit FPS |
| ENABLE_PROCESSOR | true | Enable face detection |

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| VITE_API_WS | ws://localhost:8000 | WebSocket endpoint |

## API Endpoints

- `GET /health` - Health check
- `GET /roi` - List detection ROIs
- `WebSocket /stream/input` - Stream video frames
- `WebSocket /stream/output` - Receive processed frames

## Usage

1. Allow camera access when prompted
2. The raw camera feed displays in the LIVE panel
3. Processed frames (with face bounding boxes) overlay the camera feed
4. Detection status shows below the video panel