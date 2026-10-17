"""Core per-video processing (runs inside the Modal GPU container)."""
import json
import math
import os
import subprocess
import tempfile

import numpy as np

ANALYSIS_FPS = 10.0
MAX_SECONDS = 30.0
RENDER_FPS_CAP = 30.0
FOV_DEG = 60.0
OUT_H = 720

# COCO skeleton
SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4), (0, 5), (0, 6)]
POSTURES = ["upright", "stooped", "crouching", "lying", "arms_overhead"]
STATUS_BGR = {"green": (120, 255, 80), "amber": (0, 190, 255), "red": (80, 60, 255)}


def clip01(x):
    return float(min(1.0, max(0.0, x)))


# ---------------------------------------------------------------- geometry
def intrinsics(w, h):
    f = (w / 2.0) / math.tan(math.radians(FOV_DEG) / 2.0)
    return f, w / 2.0, h / 2.0


def backproject(u, v, z, f, cx, cy):
    """Camera frame, X right, Y up, Z = -depth (three.js style, camera looks down -Z)."""
    X = (u - cx) * z / f
    Y = -(v - cy) * z / f
    return np.stack([X, Y, -z], -1)


def rot_to_y(n):
    n = n / (np.linalg.norm(n) + 1e-9)
    t = np.array([0.0, 1.0, 0.0])
    v = np.cross(n, t)
    c = float(np.dot(n, t))
    if np.linalg.norm(v) < 1e-6:
        return np.eye(3) if c > 0 else np.diag([1, -1, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def ransac_plane(P, iters=300, thr=0.15, rng=None):
    rng = rng or np.random.default_rng(0)
    best, best_in = None, 0
    if len(P) < 50:
        return None
    for _ in range(iters):
        s = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(s[1] - s[0], s[2] - s[0])
        nn = np.linalg.norm(n)
        if nn < 1e-6:
            continue
        n /= nn
        if n[1] < 0:
            n = -n
        if n[1] < 0.5:  # reject near-vertical planes
            continue
        d = -np.dot(n, s[0])
        inl = np.abs(P @ n + d) < thr
        k = int(inl.sum())
        if k > best_in:
            best_in, best = k, (n, d, inl)
    return best


# ---------------------------------------------------------------- depth
def run_depth(frames_rgb, dproc, dmodel, device):
    import torch
    out = []
    for i in range(0, len(frames_rgb), 8):
        batch = frames_rgb[i:i + 8]
        inp = dproc(images=batch, return_tensors="pt")
        pv = inp["pixel_values"].to(device)
        if device == "cuda":
            pv = pv.half()
        with torch.no_grad():
            pred = dmodel(pixel_values=pv).predicted_depth.float()
        h, w = batch[0].shape[:2]
        pred = torch.nn.functional.interpolate(pred[:, None], size=(h, w), mode="bilinear", align_corners=False)[:, 0]
        out.extend(list(pred.cpu().numpy()))
    return out


# ---------------------------------------------------------------- per-person signals
def angle(a, b, c):
    ba, bc = a - b, c - b
    cosv = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    return math.degrees(math.acos(max(-1, min(1, cosv))))


def pose_metrics(k):
    """k: 17x3 (x,y,conf) image coords. returns dict of raw pose measures."""
    xy = k[:, :2]
    c = k[:, 2]
    ok = lambda *ids: all(c[i] > 0.3 for i in ids)
    sh = (xy[5] + xy[6]) / 2
    hp = (xy[11] + xy[12]) / 2
    shw = max(np.linalg.norm(xy[5] - xy[6]), 1e-3)
    torso_len = max(np.linalg.norm(sh - hp), 1e-3)
    scale = max(shw, torso_len * 0.6)
    m = {"droop": 0.0, "torso_deg": 0.0, "knee_deg": 175.0, "hand_face": 0.0, "arms_up": False}
    if ok(0, 5, 6):
        # nose normally ~0.5*scale above shoulder line; droop when it sinks toward/below shoulders
        rel = (xy[0, 1] - sh[1]) / scale  # negative = above
        m["droop"] = clip01((rel + 0.55) / 0.6)
        for w in (9, 10):
            if c[w] > 0.3 and np.linalg.norm(xy[w] - xy[0]) < 0.6 * scale:
                m["hand_face"] = 1.0
            if c[w] > 0.3 and xy[w, 1] < xy[0, 1] - 0.2 * scale:
                m["arms_up"] = True
    if ok(5, 6, 11, 12):
        v = sh - hp
        m["torso_deg"] = math.degrees(math.atan2(abs(v[0]), -v[1] + 1e-9)) if -v[1] > 0 else 90 + math.degrees(math.atan2(v[1], abs(v[0]) + 1e-9))
    knees = []
    for a, b, cc in ((11, 13, 15), (12, 14, 16)):
        if ok(a, b, cc):
            knees.append(angle(xy[a], xy[b], xy[cc]))
    if knees:
        m["knee_deg"] = float(np.mean(knees))
    return m


def classify_posture(m):
    if m["torso_deg"] > 72 and m.get("wide", False):
        return "lying"
    if m["knee_deg"] < 115:
        return "crouching"
    if m["arms_up"]:
        return "arms_overhead"
    if m["torso_deg"] > 28:
        return "stooped"
    return "upright"


# ---------------------------------------------------------------- scene
KP_CONF = 0.35


def kp_valid(k, conf=KP_CONF):
    """Valid keypoints: confident and not collapsed at/near the image origin."""
    return (k[:, 2] >= conf) & ((k[:, 0] > 3) | (k[:, 1] > 3))


def fuse_depth(depths, rgbs, masks, kf):
    """Per-pixel nan-median over frames (people masked out). Only frames consistent with a static camera."""
    import cv2
    import warnings
    g0 = cv2.cvtColor(rgbs[kf], cv2.COLOR_RGB2GRAY).astype(np.float32)
    use = []
    for i in range(len(depths)):
        gi = cv2.cvtColor(rgbs[i], cv2.COLOR_RGB2GRAY).astype(np.float32)
        free = ~(masks[i] | masks[kf])
        diff = float(np.mean(np.abs(gi - g0)[free])) if free.any() else 99.0
        if i == kf or diff < 14.0:
            use.append(i)
    D = np.stack([np.where(masks[i], np.nan, depths[i]) for i in use]).astype(np.float32)
    C = np.stack([np.where(masks[i][..., None], np.nan, rgbs[i].astype(np.float32)) for i in use])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dz = np.nanmedian(D, 0)
        col = np.nanmedian(C, 0)
    # pixels occluded by people in every frame: fall back to keyframe depth/colour
    miss = ~np.isfinite(dz)
    dz[miss] = depths[kf][miss]
    col[miss] = rgbs[kf][miss]
    return dz, col, len(use)


def voxel_down(P, C, target):
    lo = P.min(0)
    ext = float(np.max(P.max(0) - lo)) + 1e-6
    vs = ext / 700.0
    for it in range(6):
        q = np.floor((P - lo) / vs).astype(np.int64)
        key = (q[:, 0] * 73856093) ^ (q[:, 1] * 19349663) ^ (q[:, 2] * 83492791)
        uk, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
        if len(uk) <= target * 1.05 or it == 5:
            break
        vs *= math.sqrt(len(uk) / target) * 1.02
    Ps = np.zeros((len(uk), 3))
    Cs = np.zeros((len(uk), 3))
    np.add.at(Ps, inv, P)
    np.add.at(Cs, inv, C)
    return Ps / cnt[:, None], Cs / cnt[:, None], vs


def sor(P, k=8, std=2.0):
    from scipy.spatial import cKDTree
    if len(P) < 100:
        return np.ones(len(P), bool)
    d, _ = cKDTree(P).query(P, k=k + 1, workers=-1)
    m = d[:, 1:].mean(1)
    return m < m.mean() + std * m.std()


def heightmap_edges(Pr, max_cells=200, drop_thr=0.8, search=8):
    """Top-down grid of max height; drop edges where a cell is > drop_thr above the next observed cell."""
    import cv2
    import warnings
    x, y, z = Pr[:, 0], Pr[:, 1], Pr[:, 2]
    x0, x1 = np.percentile(x, [0.5, 99.5])
    z0, z1 = np.percentile(z, [0.5, 99.5])
    cell = max(0.08, max(x1 - x0, z1 - z0) / max_cells)
    W = int((x1 - x0) / cell) + 1
    H = int((z1 - z0) / cell) + 1
    ix = np.floor((x - x0) / cell).astype(int)
    iz = np.floor((z - z0) / cell).astype(int)
    ok = (ix >= 0) & (ix < W) & (iz >= 0) & (iz < H)
    lin = iz[ok] * W + ix[ok]
    hm = np.full(H * W, -np.inf)
    np.maximum.at(hm, lin, y[ok])
    cnt = np.bincount(lin, minlength=H * W)
    hm[cnt < 2] = np.nan
    hm = hm.reshape(H, W)
    hm[~np.isfinite(hm)] = np.nan
    pad = np.pad(hm, 1, constant_values=np.nan)
    stack = np.stack([pad[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)])
    nval = np.isfinite(stack).sum(0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nanmedian(stack, 0)
    hole = ~np.isfinite(hm) & (nval >= 5)
    hm[hole] = med[hole]
    valid = np.isfinite(hm)
    E = np.zeros((H, W), bool)
    DROP = np.zeros((H, W))
    big = np.pad(hm, search, constant_values=np.nan)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        found = np.zeros((H, W), bool)
        nb = np.full((H, W), np.nan)
        for s_ in range(1, search + 1):
            sh = big[search + dy * s_: search + dy * s_ + H, search + dx * s_: search + dx * s_ + W]
            take = ~found & np.isfinite(sh)
            nb[take] = sh[take]
            found |= take
        with np.errstate(invalid="ignore"):
            d = hm - nb
        hit = valid & found & (np.nan_to_num(d) > drop_thr)
        E |= hit
        DROP = np.where(hit, np.fmax(DROP, np.nan_to_num(d)), DROP)
    E = cv2.morphologyEx(E.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool) & valid
    ncomp, lab, stats, _ = cv2.connectedComponentsWithStats(E.astype(np.uint8), connectivity=8)
    cands = []
    for ci in range(1, ncomp):
        if stats[ci, cv2.CC_STAT_AREA] < 3:
            continue
        rr, cc = np.nonzero(lab == ci)
        drops = DROP[rr, cc]
        drops = drops[drops > 0]
        if not len(drops):
            continue
        drop = float(min(40.0, np.median(drops)))
        X = np.stack([x0 + (cc + 0.5) * cell, z0 + (rr + 0.5) * cell], 1)
        Yh = hm[rr, cc]
        mu = X.mean(0)
        _, _, vt = np.linalg.svd(X - mu, full_matrices=False)
        tpar = (X - mu) @ vt[0]
        order = np.argsort(tpar)
        bins = np.array_split(order, min(20, max(2, len(order) // 2)))
        poly = [[round(float(X[b, 0].mean()), 3), round(float(Yh[b].max()), 3), round(float(X[b, 1].mean()), 3)]
                for b in bins if len(b)]
        length = float(tpar.max() - tpar.min()) + cell
        cands.append((drop * math.sqrt(len(rr)), {"polyline": poly, "drop_m": round(drop, 2)}, X, Yh, length))
    cands.sort(key=lambda c: -c[0])
    cands = cands[:6]
    edges = [c[1] for c in cands]
    zones = []
    for _, e, X, Yh, length in cands:
        c = X.mean(0)
        zones.append({"center": [round(float(c[0]), 3), round(float(np.median(Yh)), 3), round(float(c[1]), 3)],
                      "radius": round(float(max(1.0, min(8.0, length / 2 + 0.5))), 2), "drop_m": e["drop_m"]})
    edge_pts = np.concatenate([np.c_[X[:, 0], Yh, X[:, 1]] for _, _, X, Yh, _ in cands]) if cands else np.zeros((0, 3))
    hmeta = {"origin": [round(float(x0), 4), round(float(z0), 4)], "cell": round(float(cell), 4), "w": int(W), "h": int(H),
             "file": "heightmap.bin",
             "layout": "float32 LE, row-major [h][w]; row j -> z = origin[1] + (j+0.5)*cell, col i -> x = origin[0] + (i+0.5)*cell; value = max world Y (m), NaN = empty"}
    return edges, zones, edge_pts, hm.astype("<f4"), hmeta


def build_scene(frames_rgb, depths, masks, kf, rng, target_pts=250000, col_hw=None, col_frames=None):
    """Inputs at depth resolution (dh, dw). Returns scene dict, points bin, R, ground_y, edge_pts, heightmap bytes."""
    import cv2
    dz, colf, n_used = fuse_depth(depths, frames_rgb, masks, kf)
    h, w = dz.shape
    zf = dz.astype(np.float32)
    # flying-pixel mask: strong relative depth gradient
    gx = np.abs(cv2.Sobel(zf, cv2.CV_32F, 1, 0, ksize=3)) / 8
    gy = np.abs(cv2.Sobel(zf, cv2.CV_32F, 0, 1, ksize=3)) / 8
    rel = np.maximum(gx, gy) / np.maximum(zf, 0.3)
    fly = cv2.dilate((rel > 0.035).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    hi = np.percentile(zf, 98)
    valid = (zf > 0.3) & (zf < hi) & ~fly
    ch, cw = col_hw or (h, w)
    if (ch, cw) != (h, w):
        dz_u = cv2.resize(zf, (cw, ch), interpolation=cv2.INTER_LINEAR)
        val_u = cv2.resize(valid.astype(np.uint8), (cw, ch), interpolation=cv2.INTER_NEAREST).astype(bool)
        col_u = cv2.resize(colf.astype(np.float32), (cw, ch), interpolation=cv2.INTER_LINEAR)
        if col_frames is not None:
            # sharper colour from the full-res keyframe, except where people were (keep fused colour there)
            pm = cv2.resize(masks[kf].astype(np.uint8), (cw, ch), interpolation=cv2.INTER_NEAREST).astype(bool)
            col_u[~pm] = col_frames[~pm]
    else:
        dz_u, val_u, col_u = zf, valid, colf
    f, cx, cy = intrinsics(cw, ch)
    vv, uu = np.mgrid[0:ch, 0:cw]
    P = backproject(uu[val_u].astype(np.float32), vv[val_u].astype(np.float32), dz_u[val_u], f, cx, cy)
    C = col_u[val_u] / 255.0
    rows = vv[val_u]
    gm = rows > ch * 0.55
    G = P[gm] if gm.sum() > 200 else P
    if len(G) > 5000:
        G = G[rng.choice(len(G), 5000, replace=False)]
    res = ransac_plane(G, iters=400, thr=max(0.08, float(np.median(-G[:, 2])) * 0.02), rng=rng) if len(G) else None
    if res is None:
        n, d = np.array([0, 1.0, 0]), -float(np.percentile(P[:, 1], 5))
    else:
        n, d = res[0], res[1]
    R = rot_to_y(n)
    ground_y = float(-d)
    Pr = P @ R.T
    Pv, Cv, vs = voxel_down(Pr, C, target_pts)
    keep = sor(Pv)
    Pv, Cv = Pv[keep], Cv[keep]
    if len(Pv) > target_pts:
        sel = rng.choice(len(Pv), target_pts, replace=False)
        Pv, Cv = Pv[sel], Cv[sel]
    edges, zones, edge_pts, hm, hmeta = heightmap_edges(Pv)
    buf = np.concatenate([Pv, Cv.clip(0, 1)], 1).astype("<f4")
    # cinematic intro camera: behind + above the original camera, orbited ~28 deg, looking at the scene centre
    target = np.median(Pv, 0)
    target[1] = ground_y + 0.15 * (float(np.percentile(Pv[:, 1], 95)) - ground_y)
    back = -target.copy()
    back[1] = 0
    dist = max(3.0, float(np.linalg.norm(back)))
    back = back / (np.linalg.norm(back) + 1e-9)
    a = math.radians(28)
    rot = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    pos = target + rot @ back * dist * 1.25
    pos[1] = max(0.0, ground_y) + dist * 0.55
    fwd = R @ np.array([0, 0, -1.0])
    scene = {
        "points": "scene_points.bin", "n_points": int(len(Pv)),
        "bounds": {"min": Pv.min(0).round(3).tolist(), "max": Pv.max(0).round(3).tolist()},
        "ground_y": round(float(ground_y), 3), "edges": edges,
        "camera": {"fov": FOV_DEG, "position": [0, 0, 0], "forward": np.round(fwd, 4).tolist()},
        "up": [0, 1, 0],
        "hazard_zones": zones,
        "heightmap": hmeta,
        "intro_camera": {"position": np.round(pos, 3).tolist(), "target": np.round(target, 3).tolist()},
        "fusion": {"frames": int(n_used), "voxel_m": round(float(vs), 4)},
    }
    return scene, buf.tobytes(), R, ground_y, edge_pts, hm.tobytes()


# ---------------------------------------------------------------- rendering helpers
def rrect(img, x1, y1, x2, y2, r, col):
    import cv2
    r = int(max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2)))
    cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), col, -1)
    cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), col, -1)
    for cx_, cy_ in ((x1 + r, y1 + r), (x2 - r, y1 + r), (x1 + r, y2 - r), (x2 - r, y2 - r)):
        cv2.circle(img, (cx_, cy_), r, col, -1, cv2.LINE_AA)


def draw_hud(img, t, n_workers, metrics, status, n_edges):
    """metrics: list of (label, value 0..1, bgr)."""
    import cv2
    h, w = img.shape[:2]
    S = max(0.6, h / 720.0)
    F = cv2.FONT_HERSHEY_SIMPLEX
    x0, y0 = int(16 * S), int(16 * S)
    pw = int(300 * S)
    row = int(24 * S)
    ph = int(46 * S) + row * len(metrics) + int(28 * S)
    ov = img.copy()
    rrect(ov, x0, y0, x0 + pw, y0 + ph, int(10 * S), (24, 17, 12))
    cv2.addWeighted(ov, 0.7, img, 0.3, 0, img)
    col = STATUS_BGR[status]
    cv2.rectangle(img, (x0, y0 + int(10 * S)), (x0 + max(2, int(3 * S)), y0 + ph - int(10 * S)), col, -1)
    pad = int(14 * S)
    fs_t, fs = 0.5 * S, 0.42 * S
    th = max(1, int(round(S)))
    cv2.putText(img, "SITEMIND", (x0 + pad, y0 + int(24 * S)), F, fs_t, (255, 255, 255), th, cv2.LINE_AA)
    (tw, _), _ = cv2.getTextSize("SITEMIND", F, fs_t, th)
    cv2.circle(img, (x0 + pad + tw + int(10 * S), y0 + int(19 * S)), max(2, int(3.5 * S)), (80, 80, 255), -1, cv2.LINE_AA)
    cv2.putText(img, "LIVE", (x0 + pad + tw + int(17 * S), y0 + int(24 * S)), F, fs, (190, 190, 190), 1, cv2.LINE_AA)
    rt = f"T+{t:04.1f}s  {n_workers} WKR"
    (rw, _), _ = cv2.getTextSize(rt, F, fs, 1)
    cv2.putText(img, rt, (x0 + pw - pad - rw, y0 + int(24 * S)), F, fs, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.line(img, (x0 + pad, y0 + int(34 * S)), (x0 + pw - pad, y0 + int(34 * S)), (75, 70, 65), 1, cv2.LINE_AA)
    lab_w, val_w = int(98 * S), int(44 * S)
    bx1, bx2 = x0 + pad + lab_w, x0 + pw - pad - val_w
    bh = max(4, int(6 * S))
    for i, (lab, v, c) in enumerate(metrics):
        cy_ = y0 + int(52 * S) + row * i
        cv2.putText(img, lab, (x0 + pad, cy_ + int(5 * S)), F, fs, (215, 215, 215), 1, cv2.LINE_AA)
        rrect(img, bx1, cy_ - bh // 2, bx2, cy_ + bh // 2, bh // 2, (62, 56, 50))
        fill = bx1 + int((bx2 - bx1) * clip01(v))
        if fill > bx1 + bh:
            rrect(img, bx1, cy_ - bh // 2, fill, cy_ + bh // 2, bh // 2, c)
        vt = f"{v:.2f}"
        (vw, _), _ = cv2.getTextSize(vt, F, fs, 1)
        cv2.putText(img, vt, (x0 + pw - pad - vw, cy_ + int(5 * S)), F, fs, c, 1, cv2.LINE_AA)
    fy = y0 + ph - int(11 * S)
    cv2.putText(img, f"STATUS {status.upper()}", (x0 + pad, fy), F, fs, col, th, cv2.LINE_AA)
    et = f"DROP EDGES {n_edges}"
    (ew, _), _ = cv2.getTextSize(et, F, fs, 1)
    cv2.putText(img, et, (x0 + pw - pad - ew, fy), F, fs, (0, 190, 255) if n_edges else (160, 160, 160), 1, cv2.LINE_AA)


def corner_box(img, x1, y1, x2, y2, col, t=2):
    import cv2
    L = int(max(8, min(x2 - x1, y2 - y1) * 0.22))
    for (px, py, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(img, (px, py), (px + dx * L, py), col, t, cv2.LINE_AA)
        cv2.line(img, (px, py), (px, py + dy * L), col, t, cv2.LINE_AA)


def ffmpeg_encode(frames_dir, fps, out_path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:.3f}", "-i", os.path.join(frames_dir, "%05d.jpg"),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-movflags", "+faststart", out_path], check=True)


# ---------------------------------------------------------------- main
def process(video_bytes, video_id, meta_extra, pose, dproc, dmodel, device):
    import cv2
    rng = np.random.default_rng(0)
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "in.mp4")
    with open(src, "wb") as fh:
        fh.write(video_bytes)
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not (1 < fps < 240):
        fps = 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    rstep = max(1, int(round(fps / RENDER_FPS_CAP)))
    rfps = fps / rstep
    astep = max(1, int(round(rfps / ANALYSIS_FPS)))  # analysis every astep rendered frames
    max_frames = int(MAX_SECONDS * fps)

    # ---- pass 1: read frames (render rate), pose+track on all of them
    scale = min(1.0, OUT_H / H)
    ow, oh = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    frames = []  # downscaled BGR frames
    poses = []   # list of list of (tid, bbox_orig, kpts_orig)
    idx = 0
    while idx < max_frames:
        ok, fr = cap.read()
        if not ok:
            break
        if idx % rstep == 0:
            res = pose.track(fr, persist=True, tracker="bytetrack.yaml", classes=[0], conf=0.25, verbose=False, device=0 if device == "cuda" else "cpu")[0]
            ps = []
            if res.boxes is not None and len(res.boxes):
                bx = res.boxes.xyxy.cpu().numpy()
                ids = res.boxes.id.cpu().numpy().astype(int) if res.boxes.id is not None else -np.arange(1, len(bx) + 1)
                kp = res.keypoints.data.cpu().numpy() if res.keypoints is not None else np.zeros((len(bx), 17, 3))
                for b, t, k in zip(bx, ids, kp):
                    k = k.copy()
                    k[(k[:, 0] <= 3) & (k[:, 1] <= 3), 2] = 0.0  # YOLO emits (0,0) for missing joints
                    ps.append((int(t), b, k))
            poses.append(ps)
            frames.append(cv2.resize(fr, (ow, oh), interpolation=cv2.INTER_AREA) if scale < 1 else fr)
        idx += 1
    cap.release()
    n_r = len(frames)
    if n_r == 0:
        raise RuntimeError("no frames decoded")
    duration = idx / fps

    # ---- depth on analysis frames (at reduced res)
    a_idx = list(range(0, n_r, astep))
    dw = 518 if ow >= oh else int(518 * ow / oh)
    dh = int(dw * oh / ow)
    small = [cv2.cvtColor(cv2.resize(frames[i], (dw, dh)), cv2.COLOR_BGR2RGB) for i in a_idx]
    depths = run_depth(small, dproc, dmodel, device)
    sx, sy = dw / W, dh / H
    f, cx, cy = intrinsics(dw, dh)

    # ---- scene from a keyframe: median depth of a few frames, people masked
    pick = sorted(set(np.linspace(0, len(a_idx) - 1, min(7, len(a_idx))).astype(int).tolist()))
    kpi = pick[len(pick) // 2]
    masks = []
    for i in pick:
        pm = np.zeros((dh, dw), bool)
        for _, b, _ in poses[a_idx[i]]:
            x1, y1, x2, y2 = (b * [sx, sy, sx, sy]).astype(int)
            mx, my = int((x2 - x1) * 0.1) + 2, int((y2 - y1) * 0.06) + 2
            pm[max(0, y1 - my):y2 + my, max(0, x1 - mx):x2 + mx] = True
        masks.append(pm)
    cw = min(ow, 960) // 2 * 2
    ch = int(round(cw * oh / ow)) // 2 * 2
    kf_hi = cv2.cvtColor(cv2.resize(frames[a_idx[kpi]], (cw, ch), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(np.float32)
    scene, pts_bin, R, ground_y, edge_pts, hm_bin = build_scene(
        [small[i] for i in pick], [depths[i] for i in pick], masks, pick.index(kpi), rng,
        target_pts=250000, col_hw=(ch, cw), col_frames=kf_hi)
    edge_xz = edge_pts[:, [0, 2]] if len(edge_pts) else None

    # ---- per analysis frame person features
    track_hist = {}  # tid -> list of (frame_i, kpts_norm, center)
    frames_out = []
    raw_rows = []  # for features
    prev = {}
    still = {}
    ema = {}
    for ai, ri in enumerate(a_idx):
        D = depths[ai]
        t = round(ri * rstep / fps, 3)
        plist = []
        feet3d = {}
        for tid, b, k in poses[ri]:
            m = pose_metrics(k)
            m["wide"] = (b[2] - b[0]) > (b[3] - b[1]) * 1.1
            p_post = classify_posture(m)
            # motion: mean keypoint displacement normalised by bbox height
            bh = max(b[3] - b[1], 1.0)
            if tid in prev:
                pk = prev[tid]
                good = (k[:, 2] > 0.3) & (pk[:, 2] > 0.3)
                mot = float(np.linalg.norm(k[good, :2] - pk[good, :2], axis=1).mean() / bh) if good.any() else 0.0
            else:
                mot = 0.03
            prev[tid] = k
            motion_e = clip01(mot / 0.04)
            still[tid] = still.get(tid, 0) + 1 if motion_e < 0.2 else 0
            stillness = clip01(still[tid] / (ANALYSIS_FPS * 4))
            # 3D lifting
            u = np.clip(k[:, 0] * sx, 0, dw - 1)
            v = np.clip(k[:, 1] * sy, 0, dh - 1)
            x1, y1, x2, y2 = (b * [sx, sy, sx, sy]).astype(int)
            cxb, cyb = (x1 + x2) // 2, (y1 + y2) // 2
            zk = D[v.astype(int), u.astype(int)]
            kv = kp_valid(k)
            if kv.sum() >= 3:
                zc = float(np.median(zk[kv]))
            else:
                reg = D[max(0, cyb - 3):cyb + 4, max(0, cxb - 3):cxb + 4]
                zc = float(np.median(reg)) if reg.size else float(np.median(D))
            zk = np.where(kv, np.clip(zk, zc - 0.6, zc + 0.6), zc)
            k3 = backproject(u, v, zk, f, cx, cy) @ R.T
            if (~kv).any():  # park missing joints at the body centre instead of the image corner
                cb = backproject(np.array([float(cxb)]), np.array([float(cyb)]), np.array([zc]), f, cx, cy) @ R.T
                k3[~kv] = k3[kv].mean(0) if kv.any() else cb[0]
            foot = k3[[15, 16]][kv[[15, 16]]]
            fy = float(foot[:, 1].min()) if len(foot) else float((backproject(np.array([float(cxb)]), np.array([float(min(y2, dh - 1))]), np.array([zc]), f, cx, cy) @ R.T)[0, 1])
            height_m = max(0.0, fy - ground_y)
            ctr = k3[[11, 12]].mean(0)
            feet3d[tid] = ctr
            near = False
            if edge_xz is not None and len(edge_xz):
                dist = np.min(np.linalg.norm(edge_xz - ctr[[0, 2]], axis=1))
                near = bool(dist < 2.0)
            posture = p_post
            plist.append(dict(track_id=tid, bbox=[round(float(x), 1) for x in b], kpts=np.round(k, 2).tolist(),
                              kpts3d=np.round(k3, 3).tolist(), _m=m, _motion=motion_e, _still=stillness,
                              posture=posture, height_m=round(height_m, 2), near_edge=near))
        # isolation needs everyone in the frame
        for p in plist:
            tid = p["track_id"]
            others = [feet3d[o] for o in feet3d if o != tid]
            if others:
                dmin = min(np.linalg.norm(feet3d[tid][[0, 2]] - o[[0, 2]]) for o in others)
                iso = clip01((dmin - 2.0) / 8.0)
            else:
                iso = 0.6
            m = p.pop("_m")
            mot = p.pop("_motion")
            st = p.pop("_still")
            stoop = clip01(m["torso_deg"] / 60.0)
            fat = 0.35 * m["droop"] + 0.2 * stoop + 0.2 * (1 - mot) + 0.15 * st + 0.1 * m["hand_face"]
            wd = 0.4 * iso + 0.3 * m["droop"] + 0.3 * (1 - mot)
            hr = clip01(0.6 * clip01(p["height_m"] / 4.0) + 0.4 * float(p["near_edge"]) * (0.5 + 0.5 * clip01(p["height_m"] / 2)))
            e = ema.get(tid, (fat, wd))
            e = (0.7 * e[0] + 0.3 * fat, 0.7 * e[1] + 0.3 * wd)
            ema[tid] = e
            p["fatigue"], p["withdrawal"] = round(clip01(e[0]), 3), round(clip01(e[1]), 3)
            p["risk"] = round(clip01(0.45 * e[0] + 0.2 * e[1] + 0.55 * hr), 3)
            p["_hr"] = hr
            raw_rows.append([p["fatigue"], p["withdrawal"], p["risk"], p["height_m"], m["droop"], stoop, mot, m["hand_face"],
                             m["torso_deg"], m["knee_deg"], iso, st, float(p["near_edge"]), hr] +
                            [float(p["posture"] == q) for q in POSTURES])
            track_hist.setdefault(tid, []).append(dict(f=p["fatigue"], w=p["withdrawal"], hr=hr, droop=m["droop"], mot=mot,
                                                       iso=iso, near=p["near_edge"], stoop=stoop, hf=m["hand_face"], st=st,
                                                       h=p["height_m"]))
        frames_out.append({"t": t, "persons": plist})

    # ---- per-worker aggregates
    workers = []
    for tid, hist in track_hist.items():
        if len(hist) < 6:
            continue
        g = lambda k: float(np.mean([x[k] for x in hist]))
        fat, wd, hr = g("f"), g("w"), float(np.percentile([x["hr"] for x in hist], 80))
        overall = clip01(0.45 * fat + 0.2 * wd + 0.55 * hr)
        flags = []
        if g("droop") > 0.45: flags.append("head drooping")
        if g("mot") < 0.3: flags.append("slow movement")
        if g("st") > 0.5: flags.append("long periods of stillness")
        if g("stoop") > 0.45: flags.append("stooped posture")
        if g("hf") > 0.25: flags.append("hand to face often")
        if g("iso") > 0.5: flags.append("isolated from crew")
        if g("near") > 0.2: flags.append("working near drop edge")
        if g("h") > 2.0: flags.append(f"working at height (~{g('h'):.1f} m)")
        status = "red" if overall > 0.5 else "amber" if overall > 0.3 else "green"
        workers.append(dict(track_id=tid, fatigue=round(fat, 3), withdrawal=round(wd, 3), height_risk=round(hr, 3),
                            overall=round(overall, 3), status=status, flags=flags, n_frames=len(hist)))
    workers.sort(key=lambda x: -x["overall"])
    wstat = {w["track_id"]: w["status"] for w in workers}

    def mean_of(k):
        return round(float(np.mean([w[k] for w in workers])), 3) if workers else 0.0
    s_over = round(max([w["overall"] for w in workers], default=0.0) * 0.6 + mean_of("overall") * 0.4, 3)
    status = "red" if s_over > 0.5 else "amber" if s_over > 0.3 else "green"
    if not workers:
        headline = "No workers clearly visible in this clip."
    else:
        top = workers[0]
        n_flag = sum(1 for w in workers if w["status"] != "green")
        if top["status"] == "green":
            headline = f"{len(workers)} worker(s) tracked; crew looks alert and settled, no concerns flagged."
        else:
            fl = ", ".join(top["flags"][:2]) or "elevated combined risk"
            headline = f"{n_flag} of {len(workers)} worker(s) worth a check-in; worker #{top['track_id']} shows {fl}."
    summary = dict(n_workers=len(workers), fatigue=mean_of("fatigue"), withdrawal=mean_of("withdrawal"),
                   height_risk=mean_of("height_risk"), overall=s_over, status=status,
                   predicted_class=None, predicted_unsafe_prob=None, headline=headline)
    timeline = {"t": [], "fatigue": [], "withdrawal": [], "risk": [], "n_persons": []}
    for fo in frames_out:
        ps = fo["persons"]
        timeline["t"].append(fo["t"])
        timeline["n_persons"].append(len(ps))
        for k in ("fatigue", "withdrawal", "risk"):
            timeline[k].append(round(float(np.mean([p[k] for p in ps])), 3) if ps else 0.0)
    for fo in frames_out:
        for p in fo["persons"]:
            p.pop("_hr", None)

    # ---- features
    names = ["fatigue", "withdrawal", "risk", "height_m", "droop", "stoop", "motion", "hand_face", "torso_deg", "knee_deg",
             "isolation", "stillness", "near_edge", "height_risk"] + [f"posture_{q}" for q in POSTURES]
    X = np.array(raw_rows, dtype=np.float32) if raw_rows else np.zeros((1, len(names)), np.float32)
    feat, fnames = [], []
    for j, nm in enumerate(names):
        col = X[:, j]
        for st_name, fn in (("mean", np.mean), ("std", np.std), ("max", np.max), ("p90", lambda a: np.percentile(a, 90))):
            if nm.startswith("posture_") and st_name != "mean":
                continue
            feat.append(float(fn(col)))
            fnames.append(f"{nm}_{st_name}")
    npers = np.array(timeline["n_persons"] or [0], np.float32)
    extra = {"n_persons_mean": float(npers.mean()), "n_persons_max": float(npers.max()), "n_tracks": float(len(track_hist)),
             "n_workers": float(len(workers)), "n_edges": float(len(scene["edges"])),
             "max_drop_m": float(max([e["drop_m"] for e in scene["edges"]], default=0.0)), "duration": float(duration),
             "frac_frames_with_person": float((npers > 0).mean())}
    for k, v in extra.items():
        feat.append(v)
        fnames.append(k)
    feat = np.nan_to_num(np.array(feat, np.float32))

    # ---- render annotated video (render rate, pose from every frame, signals from nearest analysis frame)
    import io
    adir = os.path.join(tmp, "ann"); os.makedirs(adir)
    ddir = os.path.join(tmp, "dep"); os.makedirs(ddir)
    sig = {}  # (analysis_i, tid) -> person
    for ai, fo in enumerate(frames_out):
        for p in fo["persons"]:
            sig[(ai, p["track_id"])] = p
    s = ow / W
    S = max(0.6, oh / 720.0)
    trail = {}
    smooth = {}  # tid -> (xy 17x2, valid 17, last_ri)
    TRAIL_LEN = 14
    for ri in range(n_r):
        img = frames[ri].copy()
        ai = min(len(a_idx) - 1, ri // astep)
        glow = np.zeros_like(img)
        labels = []
        seen = set()
        for tid, b, k in poses[ri]:
            seen.add(tid)
            p = sig.get((ai, tid)) or sig.get((max(0, ai - 1), tid))
            stt = wstat.get(tid, "green")
            if p is not None:
                stt = "red" if p["risk"] > 0.5 else "amber" if p["risk"] > 0.3 else "green"
            col = STATUS_BGR[stt]
            vk = kp_valid(k)
            xy = k[:, :2] * s
            bh = max(10.0, (b[3] - b[1]) * s)
            st_ = smooth.get(tid)
            if st_ is not None and ri - st_[2] <= 3:
                pxy, pv = st_[0], st_[1]
                jump = np.linalg.norm(xy - pxy, axis=1) > 0.35 * bh
                both = vk & pv & ~jump
                nxy = np.where(both[:, None], 0.5 * pxy + 0.5 * xy, xy)
            else:
                nxy = xy
            smooth[tid] = (np.where(vk[:, None], nxy, st_[0] if st_ is not None else xy), vk, ri)
            pts = nxy.astype(int)
            for a_, b_ in SKELETON:
                if vk[a_] and vk[b_]:
                    cv2.line(glow, tuple(pts[a_]), tuple(pts[b_]), col, max(3, int(7 * S)), cv2.LINE_AA)
            # trail from hip centre: only when both hips valid; reset on gaps/jumps
            tr = trail.setdefault(tid, [])
            if vk[11] and vk[12]:
                hip = tuple(((nxy[11] + nxy[12]) / 2).astype(int))
                if tr and (ri - tr[-1][1] > 2 or math.hypot(hip[0] - tr[-1][0][0], hip[1] - tr[-1][0][1]) > 0.25 * bh):
                    tr.clear()
                tr.append((hip, ri))
                del tr[:-TRAIL_LEN]
            labels.append((tid, (b * s).astype(int), pts, vk, col, p))
        for tid in list(trail):
            if tid not in seen:
                trail[tid] = [x for x in trail[tid] if ri - x[1] <= 2]
        g1 = cv2.GaussianBlur(glow, (0, 0), 6 * S)
        img = cv2.add(img, (g1.astype(np.float32) * 0.9).clip(0, 255).astype(np.uint8))
        for tid, bb, pts, vk, col, p in labels:
            tr = trail.get(tid, [])
            for i in range(1, len(tr)):
                a_w = i / max(1, len(tr) - 1)
                c2 = tuple(int(cc * (0.35 + 0.65 * a_w)) for cc in col)
                cv2.line(img, tr[i - 1][0], tr[i][0], c2, max(1, int((1 + 2 * a_w) * S)), cv2.LINE_AA)
            for a_, b_ in SKELETON:
                if vk[a_] and vk[b_]:
                    cv2.line(img, tuple(pts[a_]), tuple(pts[b_]), col, max(2, int(3 * S)), cv2.LINE_AA)
                    cv2.line(img, tuple(pts[a_]), tuple(pts[b_]), (255, 255, 255), 1, cv2.LINE_AA)
            for j in range(17):
                if vk[j]:
                    r = max(2, int((4 if j > 4 else 3) * S))
                    cv2.circle(img, tuple(pts[j]), r, col, -1, cv2.LINE_AA)
                    cv2.circle(img, tuple(pts[j]), max(1, r // 2), (255, 255, 255), -1, cv2.LINE_AA)
            x1, y1, x2, y2 = bb
            corner_box(img, x1, y1, x2, y2, col, max(1, int(2 * S)))
            fat = p["fatigue"] if p else 0.0
            lbl = f"#{tid}  {p['posture'].upper() if p else 'TRACKING'}"
            F = cv2.FONT_HERSHEY_SIMPLEX
            fs = 0.42 * S
            (tw, th), _ = cv2.getTextSize(lbl, F, fs, 1)
            bw = max(tw, int(70 * S)) + int(12 * S)
            bh_ = int(26 * S)
            tx = int(min(max(0, x1), ow - bw - 2))
            ty = int(max(2, y1 - bh_ - int(6 * S)))
            ov = img.copy()
            rrect(ov, tx, ty, tx + bw, ty + bh_, int(5 * S), (24, 17, 12))
            cv2.addWeighted(ov, 0.72, img, 0.28, 0, img)
            cv2.putText(img, lbl, (tx + int(6 * S), ty + int(13 * S)), F, fs, col, 1, cv2.LINE_AA)
            fb1, fb2 = tx + int(6 * S), tx + bw - int(6 * S)
            fy_ = ty + int(19 * S)
            bth = max(3, int(4 * S))
            rrect(img, fb1, fy_, fb2, fy_ + bth, bth // 2, (62, 56, 50))
            fc = STATUS_BGR["red" if fat > 0.55 else "amber" if fat > 0.35 else "green"]
            if fat > 0.02:
                rrect(img, fb1, fy_, fb1 + max(bth, int((fb2 - fb1) * fat)), fy_ + bth, bth // 2, fc)
            if p and p["height_m"] > 1.5:
                ht = f"{p['height_m']:.1f} m"
                cv2.putText(img, ht, (min(x2 + int(6 * S), ow - int(50 * S)), y1 + int(14 * S)), F, fs, (0, 200, 255), 1, cv2.LINE_AA)
        tl_f = timeline["fatigue"][ai]; tl_r = timeline["risk"][ai]; tl_w = timeline["withdrawal"][ai]
        fst = "red" if tl_r > 0.5 else "amber" if tl_r > 0.3 else "green"
        lvl = lambda v, a, b: STATUS_BGR["red" if v > b else "amber" if v > a else "green"]
        draw_hud(img, ri * rstep / fps, len(poses[ri]), [
            ("FATIGUE", tl_f, lvl(tl_f, .35, .55)),
            ("WITHDRAWAL", tl_w, (255, 200, 120)),
            ("RISK", tl_r, STATUS_BGR[fst]),
        ], fst, len(scene["edges"]))
        cv2.imwrite(os.path.join(adir, f"{ri:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if ri == n_r // 2:
            cv2.imwrite(os.path.join(tmp, "thumb.jpg"), cv2.resize(img, (640, int(640 * oh / ow))), [cv2.IMWRITE_JPEG_QUALITY, 85])
    ffmpeg_encode(adir, rfps, os.path.join(tmp, "annotated.mp4"))
    lo, hi = np.percentile(np.stack(depths[::max(1, len(depths) // 5)]), [2, 98])
    for ai, D in enumerate(depths):
        dn = ((1 - (D - lo) / (hi - lo + 1e-6)).clip(0, 1) * 255).astype(np.uint8)
        cm = cv2.applyColorMap(dn, cv2.COLORMAP_TURBO)
        cm = cv2.resize(cm, (ow, oh))
        cv2.imwrite(os.path.join(ddir, f"{ai:05d}.jpg"), cm, [cv2.IMWRITE_JPEG_QUALITY, 90])
    ffmpeg_encode(ddir, rfps / astep, os.path.join(tmp, "depth.mp4"))

    afps = rfps / astep
    meta = dict(id=video_id, fps=round(fps, 3), width=W, height=H, n_frames=n_total, duration=round(duration, 3),
                analysis_fps=round(afps, 3))
    meta.update(meta_extra or {})
    analysis = dict(id=video_id, fps=round(afps, 3), frames=frames_out, workers=workers, summary=summary, timeline=timeline)
    fbuf = io.BytesIO(); np.save(fbuf, feat)
    out = {
        "meta.json": json.dumps(meta).encode(),
        "analysis.json": json.dumps(analysis, separators=(",", ":")).encode(),
        "scene.json": json.dumps(scene).encode(),
        "scene_points.bin": pts_bin,
        "heightmap.bin": hm_bin,
        "features.npy": fbuf.getvalue(),
        "features.json": json.dumps({"names": fnames, "values": feat.tolist()}).encode(),
    }
    for fn in ("annotated.mp4", "depth.mp4", "thumb.jpg"):
        with open(os.path.join(tmp, fn), "rb") as fh:
            out[fn] = fh.read()
    return out
