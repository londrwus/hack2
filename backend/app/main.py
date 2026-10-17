"""SiteMind API. Run from repo root: uvicorn backend.app.main:app --port 8000"""
import json
import re
import shutil
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
UPLOADS = DATA / "uploads"
METRICS = ROOT / "backend" / "ml" / "metrics.json"
for d in (PROCESSED, UPLOADS):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SiteMind API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

JOBS: dict[str, dict] = {}
_lock = threading.Lock()


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def rebuild_index() -> list:
    """Rebuild data/processed/index.json from data/processed/*/."""
    items = []
    for d in sorted(PROCESSED.iterdir()):
        if not d.is_dir():
            continue
        meta = _read_json(d / "meta.json", {}) or {}
        analysis = _read_json(d / "analysis.json", {}) or {}
        if not meta and not analysis:
            continue
        items.append({
            "id": meta.get("id", d.name),
            "source": meta.get("source"),
            "label": meta.get("label"),
            "class_name": meta.get("class_name"),
            "thumb": f"/media/{d.name}/thumb.jpg" if (d / "thumb.jpg").exists() else None,
            "summary": analysis.get("summary"),
        })
    with _lock:
        (PROCESSED / "index.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
    return items


def _safe_id(vid: str) -> Path:
    if not re.fullmatch(r"[\w.\-]+", vid):
        raise HTTPException(400, "bad id")
    d = PROCESSED / vid
    if not d.is_dir():
        raise HTTPException(404, "video not found")
    return d


@app.get("/api/videos")
def list_videos():
    idx = _read_json(PROCESSED / "index.json")
    return idx if idx is not None else rebuild_index()


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    d = _safe_id(vid)
    return {"meta": _read_json(d / "meta.json", {}), "analysis": _read_json(d / "analysis.json", {})}


@app.get("/api/videos/{vid}/scene")
def get_scene(vid: str):
    d = _safe_id(vid)
    s = _read_json(d / "scene.json")
    if s is None:
        raise HTTPException(404, "no scene")
    return s


@app.get("/api/model")
def get_model():
    return _read_json(METRICS, {}) or {}


@app.post("/api/reindex")
def reindex():
    return rebuild_index()


def _run_job(job_id: str, path: Path, out_dir: Path):
    JOBS[job_id]["status"] = "running"
    try:
        try:
            from backend.pipeline.run_one import process_video_file
        except Exception as e:
            raise RuntimeError(f"pipeline unavailable (backend.pipeline.run_one): {e}")
        process_video_file(str(path), str(out_dir))
        rebuild_index()
        JOBS[job_id]["status"] = "done"
    except Exception as e:
        traceback.print_exc()
        JOBS[job_id].update(status="error", error=str(e))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    stem = re.sub(r"[^\w\-]", "_", Path(file.filename or "upload").stem)[:40] or "upload"
    vid = f"up_{stem}_{uuid.uuid4().hex[:6]}"
    suffix = Path(file.filename or "").suffix.lower() or ".mp4"
    path = UPLOADS / f"{vid}{suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    out_dir = PROCESSED / vid
    out_dir.mkdir(parents=True, exist_ok=True)
    JOBS[vid] = {"id": vid, "status": "queued"}
    threading.Thread(target=_run_job, args=(vid, path, out_dir), daemon=True).start()
    return {"id": vid}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


# Static mounts (StaticFiles supports Range requests for video seeking). /media/raw first.
app.mount("/media/raw", StaticFiles(directory=str(DATA)), name="raw")
app.mount("/media", StaticFiles(directory=str(PROCESSED)), name="media")
