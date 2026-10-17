"""Process all videos via the deployed Modal app. Usage: python backend/pipeline/run_all.py [--force] [glob...]"""
import sys
from pathlib import Path

import modal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, ROOT, meta_for, rebuild_index, write_outputs  # noqa: E402


def main():
    force = "--force" in sys.argv
    pats = [a for a in sys.argv[1:] if not a.startswith("--")]
    vids = []
    if pats:
        for p in pats:
            vids += sorted(ROOT.glob(p))
    else:
        for sub in ("data/safe_unsafe/data", "data/demo_mixkit", "data/extra"):
            vids += sorted((ROOT / sub).glob("*.mp4"))
    todo = [v for v in vids if force or not (PROCESSED / v.stem / "annotated.mp4").exists()]
    print(f"{len(vids)} videos, {len(todo)} to process", flush=True)
    Pipeline = modal.Cls.from_name("sitemind", "Pipeline")
    pipe = Pipeline()
    args = [(v.read_bytes(), v.stem, meta_for(v)) for v in todo]
    ok, fail = 0, []
    for v, res in zip(todo, pipe.process.starmap(args, return_exceptions=True, order_outputs=True)):
        if isinstance(res, Exception):
            fail.append((v.name, repr(res)[:300]))
            print("FAIL", v.name, repr(res)[:300], flush=True)
            continue
        write_outputs(PROCESSED / v.stem, res)
        ok += 1
        print("ok", v.name, flush=True)
    n = rebuild_index()
    print(f"done ok={ok} fail={len(fail)} index={n}")
    for f in fail:
        print(f)


if __name__ == "__main__":
    main()
