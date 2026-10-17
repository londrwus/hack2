"""SiteMind Modal GPU pipeline.

Deploy:   modal deploy backend/pipeline/modal_app.py      (app name 'sitemind')
Batch:    python backend/pipeline/run_all.py
Single:   from backend.pipeline.run_one import process_video_file
"""
import modal

APP_NAME = "sitemind"
app = modal.App(APP_NAME)

DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf"
POSE_MODEL = "/root/weights/yolo11m-pose.pt"


def _download_weights():
    import os
    import shutil
    os.makedirs("/root/weights", exist_ok=True)
    from ultralytics import YOLO
    m = YOLO("yolo11m-pose.pt")
    if os.path.exists("yolo11m-pose.pt"):
        shutil.move("yolo11m-pose.pt", POSE_MODEL)
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    AutoImageProcessor.from_pretrained(DEPTH_MODEL)
    AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL)


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.1", "torchvision==0.19.1", "ultralytics==8.3.40", "lap>=0.5.12",
        "transformers==4.46.3", "opencv-python-headless==4.10.0.84", "numpy<2", "scipy", "pillow",
    )
    .env({"HF_HOME": "/root/hf", "YOLO_CONFIG_DIR": "/root/yolocfg"})
    .run_function(_download_weights)
    .add_local_python_source("sitemind_core")
)


@app.cls(image=image, gpu="L4", timeout=1200, scaledown_window=120, max_containers=20)
class Pipeline:
    @modal.enter()
    def load(self):
        import torch
        from ultralytics import YOLO
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.pose_path = POSE_MODEL
        self.dproc = AutoImageProcessor.from_pretrained(DEPTH_MODEL)
        self.dmodel = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL).to(self.device).eval()
        if self.device == "cuda":
            self.dmodel = self.dmodel.half()

    @modal.method()
    def process(self, video_bytes: bytes, video_id: str, meta_extra: dict) -> dict:
        import sitemind_core
        from ultralytics import YOLO
        pose = YOLO(self.pose_path)  # fresh per video -> fresh tracker state
        return sitemind_core.process(video_bytes, video_id, meta_extra, pose, self.dproc, self.dmodel, self.device)


@app.function(image=image, timeout=1500)
def process_video(video_bytes: bytes, video_id: str, meta_extra: dict) -> dict:
    """Convenience function for the API (single upload)."""
    return Pipeline().process.remote(video_bytes, video_id, meta_extra)
