"""Train safe/unsafe + multiclass classifiers on pipeline features.
Run from repo root:  python backend/ml/train.py
Writes backend/ml/model.joblib, backend/ml/metrics.json, and fills
predicted_class / predicted_unsafe_prob in data/processed/*/analysis.json."""
import json, sys
from pathlib import Path
import numpy as np, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
PROC = ROOT / "data" / "processed"
OUT = Path(__file__).resolve().parent

def load_all():
    rows = []
    for d in sorted(PROC.iterdir()):
        if not (d / "features.npy").exists():
            continue
        meta = json.loads((d / "meta.json").read_text())
        x = np.nan_to_num(np.load(d / "features.npy").astype(float).ravel(), posinf=0, neginf=0)
        rows.append((d, meta, x))
    return rows

def rf(): return RandomForestClassifier(n_estimators=400, class_weight="balanced", min_samples_leaf=1, random_state=0)

def main():
    rows = load_all()
    names = json.loads((rows[0][0] / "features.json").read_text())
    if isinstance(names, dict): names = names.get("names", list(names.keys()))
    lab = [r for r in rows if r[1].get("source") == "safe_unsafe" and r[1].get("label") is not None]
    X = np.stack([r[2] for r in lab]); yc = np.array([int(r[1]["label"]) for r in lab])
    yb = (yc <= 3).astype(int)  # 1 = unsafe
    split = np.array([r[1].get("split", "train") for r in lab])
    class_names = {}
    for r in lab: class_names[int(r[1]["label"])] = r[1].get("class_name", str(r[1]["label"]))
    labels = sorted(class_names)

    # out-of-fold predictions (min class count 3 -> 3 folds)
    cvb = StratifiedKFold(3, shuffle=True, random_state=0)
    pb = cross_val_predict(rf(), X, yb, cv=cvb, method="predict_proba")[:, 1]
    pc = cross_val_predict(rf(), X, yc, cv=cvb)
    # filename split check
    tr, te = split != "test", split == "test"
    split_info = {}
    if te.sum() and len(set(yb[tr])) == 2:
        m = rf().fit(X[tr], yb[tr]); p = m.predict(X[te])
        split_info = {"binary_acc": float(accuracy_score(yb[te], p)), "binary_f1_macro": float(f1_score(yb[te], p, average="macro")),
                      "n_train": int(tr.sum()), "n_test": int(te.sum())}

    mb = rf().fit(X, yb); mc = rf().fit(X, yc)
    imp = sorted(({"name": n, "importance": float(v)} for n, v in zip(names, mb.feature_importances_)), key=lambda d: -d["importance"])
    from sklearn.metrics import balanced_accuracy_score
    ths = np.unique(pb); thr = float(max(ths, key=lambda t: balanced_accuracy_score(yb, (pb >= t).astype(int))))
    yhat_b = (pb >= thr).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(yb, yhat_b)),
        "f1": float(f1_score(yb, yhat_b, average="macro")),
        "confusion_matrix": confusion_matrix(yb, yhat_b, labels=[0, 1]).tolist(),
        "labels": ["safe", "unsafe"],
        "multiclass": {"accuracy": float(accuracy_score(yc, pc)), "f1": float(f1_score(yc, pc, average="macro")),
                       "confusion_matrix": confusion_matrix(yc, pc, labels=labels).tolist(),
                       "labels": [class_names[l] for l in labels]},
        "feature_importances": imp[:30],
        "n_train": split_info.get("n_train", len(lab)), "n_test": split_info.get("n_test", 0),
        "n_labelled": len(lab), "filename_split_eval": split_info,
        "threshold": thr, "balanced_accuracy": float(balanced_accuracy_score(yb, yhat_b)),
        "model": "RandomForest(400 trees, class_weight=balanced)",
        "notes": ("Tiny, heavily imbalanced dataset: %d labelled clips, class 0 dominates (%d) and classes 1-7 have ~3 clips each. "
                  "Headline metrics are 3-fold stratified out-of-fold predictions on all labelled clips; filename tr/te split metrics are in "
                  "filename_split_eval. Expect high variance; multiclass results are near-anecdotal. Features are hand-crafted pose/depth "
                  "aggregates from the pipeline, not learned. Labelled clips get out-of-fold predictions; other clips use the model fit on all data. "
                  "Decision threshold was tuned on the same out-of-fold probabilities (optimistic). Treat as a demo, not a validated safety model.") % (len(lab), int((yc == 0).sum())),
    }
    joblib.dump({"threshold": thr, "binary": mb, "multiclass": mc, "feature_names": names, "class_names": class_names}, OUT / "model.joblib")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))

    oof = {r[0].name: (float(pb[i]), int(pc[i])) for i, r in enumerate(lab)}
    for d, meta, x in rows:
        if d.name in oof: prob, cls = oof[d.name]
        else:
            prob = float(mb.predict_proba(x[None])[0, list(mb.classes_).index(1)]); cls = int(mc.predict(x[None])[0])
        ap = d / "analysis.json"; a = json.loads(ap.read_text())
        a["summary"]["predicted_class"] = class_names.get(cls, str(cls))
        a["summary"]["predicted_unsafe_prob"] = round(prob, 3)
        ap.write_text(json.dumps(a))
    from backend.pipeline.common import rebuild_index
    rebuild_index()
    print(json.dumps({k: metrics[k] for k in ("accuracy", "f1", "confusion_matrix")}), metrics["multiclass"]["accuracy"], split_info)

if __name__ == "__main__":
    main()
