# SiteMind

Video-based fit-for-task wellbeing and height-safety monitor for construction workers.
It detects and tracks workers, scores fatigue, withdrawal and height risk, and rebuilds the scene in 3D to show drop edges.
The scores are prompts for a supportive conversation, not diagnoses. Support lines: Lighthouse Club 0345 605 1956, Samaritans 116 123.

## Quick start

### What you need
- Python 3.12 and Node 20 or later.
- A Modal account with the CLI authenticated (`modal token new`). Modal is only needed to process new videos.
- Edge or Chrome to view the app. The annotated videos are H.264, which plain Chromium builds can't play.

### Commands (from the repo root)
```
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 1. Process videos on the Modal GPU (only needed for new videos; outputs go to data/processed/)
cd backend/pipeline && modal deploy modal_app.py && cd ../..
python backend/pipeline/run_all.py          # skips videos already done; add --force to redo them
python backend/ml/train.py                  # trains the RandomForest and writes predictions and metrics

# 2. Start the API and the UI
uvicorn backend.app.main:app --port 8000
cd frontend && npm run dev                  # open http://localhost:5173
```
If the API is down, the UI falls back to demo data in `frontend/public/mock` (`npm run mock` regenerates it).

### Architecture
```
 data/safe_unsafe, demo_mixkit, extra (*.mp4)
            |
            v
  run_all.py / run_one.py  ---->  Modal app "sitemind" (GPU)
                                   YOLO11m-pose + ByteTrack -> 2D keypoints and tracks
                                   Depth Anything V2 (metric) -> 3D keypoints, point cloud
                                   ground-plane fit -> drop edges, height above ground
                                   signals: fatigue / withdrawal / height risk
                                   rendering: annotated.mp4, depth.mp4, thumb
            |
            v
  data/processed/<id>/ {meta, analysis, scene}.json, scene_points.bin, *.mp4, features.npy
            |                                   ^
            v                                   |
  backend/ml/train.py (RandomForest) -----------+  writes predictions + metrics.json
            |
            v
  FastAPI :8000  /api/videos, /api/videos/{id}[/scene], /api/model,
                 POST /api/analyze -> background job -> run_one -> Modal
                 /media/{id}/... (processed), /media/raw/... (data/)
            |
            v
  Vite + React + shadcn/ui :5173 (proxies /api and /media)
    Site overview | Video detail (annotated video + skeleton overlay + timelines)
    3D Digital Twin (r3f point cloud, drop-edge walls, 3D skeletons) | Upload | Model
```
The binding interface between these parts is described in `docs/CONTRACT.md`. Screenshots are in `docs/screenshots/`.

## API
- `GET /api/videos`, `GET /api/videos/{id}`, `GET /api/videos/{id}/scene`, `GET /api/model`
- `POST /api/analyze` (multipart field `file`) returns `{id}`; poll `GET /api/jobs/{id}`
- `POST /api/reindex` rebuilds `data/processed/index.json`
- Static: `/media/{id}/{file}` serves data/processed, `/media/raw/...` serves data/
