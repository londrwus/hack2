"""Single-video helper for the API: process_video_file(path, out_dir) -> analysis summary dict."""
import json
import sys
from pathlib import Path

import modal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import meta_for, rebuild_index, write_outputs  # noqa: E402


def process_video_file(path, out_dir, video_id=None, update_index=True):
    path, out_dir = Path(path), Path(out_dir)
    vid = video_id or out_dir.name
    meta = meta_for(path)
    meta["source"] = meta.get("source") if meta.get("label") is not None else "upload"
    pipe = modal.Cls.from_name("sitemind", "Pipeline")()
    files = pipe.process.remote(path.read_bytes(), vid, meta)
    write_outputs(out_dir, files)
    if update_index:
        try:
            rebuild_index()
        except Exception:
            pass
    return json.loads(files["analysis.json"])["summary"]


if __name__ == "__main__":
    print(process_video_file(sys.argv[1], sys.argv[2]))
