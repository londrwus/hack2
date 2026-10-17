# SiteMind — build contract (shared by all components)

Product: video-based "fit-for-task" wellbeing & safety monitor for construction workers.
From site video we detect each worker, track pose, estimate fatigue / low-mood (withdrawal) signals,
and lift the scene into 3D to show **height / fall-edge risk**. Accuracy matters less than an impressive demo.
Framing: safety + care (signpost Lighthouse Club 0345 605 1956, Samaritans 116 123), never punitive.

## Layout
- `backend/pipeline/` — Modal GPU processing (`modal_app.py`), feature extraction, rendering
- `backend/ml/` — training of the risk/fatigue classifier on extracted features (`train.py`, model saved to `backend/ml/model.joblib`)
- `backend/app/` — FastAPI (`main.py`), run: `uvicorn backend.app.main:app --port 8000` from repo root
- `frontend/` — Vite + React + TS + Tailwind + shadcn/ui + react-three-fiber, dev on port 5173, proxies `/api` and `/media` to :8000
- `data/safe_unsafe/data/*.mp4` — 71 labelled clips, filename `<class>_<split><n>.mp4` (class 0..7, see data/safe_unsafe/README.md)
- `data/demo_mixkit/*.mp4` — construction demo clips (unlabelled); `data/extra/` — extra downloaded clips
- `data/processed/<video_id>/` — pipeline output (video_id = filename stem, e.g. `0_te1`, `13116-720`)

## Per-video outputs in `data/processed/<video_id>/`
- `meta.json`: `{id, source, label|null, class_name|null, split|null, fps, width, height, n_frames, duration}`
- `analysis.json`:
```json
{
  "id": "0_te1",
  "fps": 10,                       // analysis sample rate (frames subsampled to ~10 fps)
  "frames": [ { "t": 0.0, "persons": [ {
      "track_id": 1, "bbox": [x1,y1,x2,y2],          // pixels in original resolution
      "kpts": [[x,y,conf], ...17 COCO],
      "kpts3d": [[X,Y,Z], ...17],                     // metres-ish, camera frame lifted via depth, Y up
      "fatigue": 0.0-1.0, "withdrawal": 0.0-1.0, "posture": "upright|stooped|crouching|lying|arms_overhead",
      "height_m": 0.0,                               // est. height above lowest ground plane
      "near_edge": false, "risk": 0.0-1.0
  } ] } ],
  "workers": [ { "track_id": 1, "fatigue": 0.6, "withdrawal": 0.3, "height_risk": 0.2, "overall": 0.5,
                 "status": "green|amber|red", "flags": ["head drooping", "slow movement", "isolated from crew", "working near drop edge"] } ],
  "summary": { "n_workers": 3, "fatigue": 0.4, "withdrawal": 0.2, "height_risk": 0.5, "overall": 0.45,
               "status": "amber", "predicted_class": "...", "predicted_unsafe_prob": 0.3,
               "headline": "one-sentence human summary" },
  "timeline": { "t": [..], "fatigue": [..], "withdrawal": [..], "risk": [..], "n_persons": [..] }
}
```
- `scene.json`: 3D reconstruction from monocular depth (Depth Anything V2) of a keyframe (optionally fused across a few frames):
  `{ "points": "scene_points.bin", "n_points": N, "bounds": {"min":[x,y,z],"max":[x,y,z]}, "ground_y": float,
     "edges": [ { "polyline": [[x,y,z],...], "drop_m": float } ], "camera": {"fov": deg, "position":[0,0,0]} }`
- `scene_points.bin`: little-endian float32, N×6 interleaved `x,y,z,r,g,b` (rgb 0..1), N ≤ 200k
- `depth.mp4` (optional, colormapped depth video), `annotated.mp4` (H.264, browser playable, skeletons + HUD), `thumb.jpg`
- `features.npy` / `features.json`: per-video feature vector used by `backend/ml`

## Index
- `data/processed/index.json`: `[ {id, source, label, class_name, thumb, summary} ]`

## API (FastAPI)
- `GET /api/videos` → index.json contents
- `GET /api/videos/{id}` → `{meta, analysis}`
- `GET /api/videos/{id}/scene` → scene.json
- `GET /media/{id}/{file}` → static files from data/processed/<id>/ (also `/media/raw/...` for originals)
- `POST /api/analyze` (multipart video upload) → runs the Modal pipeline on it, returns `{id}`; `GET /api/jobs/{id}` → `{status}`
- `GET /api/model` → training metrics (from `backend/ml/metrics.json`)
