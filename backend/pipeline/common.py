import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

# order from data/safe_unsafe/README.md (classes 0-3 unsafe, 4-7 safe)
CLASS_NAMES = ["Safe Walkway Violation", "Unauthorized Intervention", "Opened Panel Cover",
               "Carrying Overload with Forklift", "Safe Walkway", "Authorized Intervention",
               "Closed Panel Cover", "Safe Carrying"]


def meta_for(path: Path) -> dict:
    stem = path.stem
    src = path.parent.name if path.parent.name != "data" else "safe_unsafe"
    m = re.match(r"^(\d)_([a-z]+)(\d+)$", stem)
    if src == "safe_unsafe" and m:
        lab = int(m.group(1))
        split = {"te": "test", "tr": "train", "va": "val"}.get(m.group(2), m.group(2))
        return {"source": "safe_unsafe", "label": lab, "class_name": CLASS_NAMES[lab], "split": split,
                "unsafe": lab < 4}
    return {"source": src, "label": None, "class_name": None, "split": None}


def write_outputs(out_dir: Path, files: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, v in files.items():
        (out_dir / k).write_bytes(v)


def rebuild_index():
    rows = []
    for d in sorted(PROCESSED.iterdir()):
        if not (d / "analysis.json").exists():
            continue
        meta = json.loads((d / "meta.json").read_text())
        summ = json.loads((d / "analysis.json").read_text())["summary"]
        rows.append({"id": d.name, "source": meta.get("source"), "label": meta.get("label"),
                     "class_name": meta.get("class_name"), "thumb": f"/media/{d.name}/thumb.jpg", "summary": summ})
    (PROCESSED / "index.json").write_text(json.dumps(rows, indent=1))
    return len(rows)
