// Generates contract-shaped mock fixtures into public/mock/ so the UI works without the API.
// Run: node scripts/gen-mock.mjs
import fs from "fs"
import path from "path"
import { fileURLToPath } from "url"

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "mock")
fs.mkdirSync(root, { recursive: true })

let seed = 7
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v))

// COCO-17 template in metres (Y up), person facing +Z
const T = [
  [0, 1.62, 0.08], [-0.04, 1.66, 0.06], [0.04, 1.66, 0.06], [-0.08, 1.63, 0], [0.08, 1.63, 0],
  [-0.2, 1.42, 0], [0.2, 1.42, 0], [-0.26, 1.12, 0.03], [0.26, 1.12, 0.03], [-0.28, 0.85, 0.08], [0.28, 0.85, 0.08],
  [-0.12, 0.95, 0], [0.12, 0.95, 0], [-0.13, 0.5, 0.03], [0.13, 0.5, 0.03], [-0.13, 0.06, 0], [0.13, 0.06, 0],
]

const videos = [
  { id: "4_tr3", source: "safe_unsafe", label: 4, class_name: "unsafe_height_no_harness", status: "red" },
  { id: "0_te1", source: "safe_unsafe", label: 0, class_name: "safe_walkway", status: "green" },
  { id: "13116-720", source: "demo_mixkit", label: null, class_name: null, status: "amber" },
  { id: "2_tr7", source: "safe_unsafe", label: 2, class_name: "unsafe_fatigue", status: "amber" },
  { id: "worker-roof-16393893", source: "extra", label: null, class_name: null, status: "red" },
  { id: "1_te4", source: "safe_unsafe", label: 1, class_name: "safe_ppe", status: "green" },
]
const W = 1280, H = 720, FPS = 10, DUR = 12
const base = { green: 0.2, amber: 0.5, red: 0.78 }
const headlines = {
  green: "Crew looks alert and well-paced; no height concerns detected.",
  amber: "One worker shows signs of tiredness — worth a friendly check-in before heavy tasks.",
  red: "Worker near an unprotected 6 m drop showing fatigue cues — pause height work and check in.",
}
const statusOf = (v) => (v > 0.65 ? "red" : v > 0.4 ? "amber" : "green")

function project([X, Y, Z]) {
  const zc = Z + 9 // camera at z=-9 looking +z
  const f = 900
  return [W / 2 + (X * f) / zc, H * 0.62 - ((Y - 1.2) * f) / zc]
}

const index = []
for (const v of videos) {
  const b = base[v.status]
  const nP = 2 + Math.floor(rnd() * 3)
  const people = Array.from({ length: nP }, (_, i) => ({
    id: i + 1,
    x0: -4 + i * 2.6 + rnd(), z0: -1 + rnd() * 4,
    vx: (rnd() - 0.5) * 0.5, vz: (rnd() - 0.5) * 0.3,
    onSlab: v.status === "red" && i === 0,
    f: clamp(b + (rnd() - 0.5) * 0.35 + (i === 0 ? 0.12 : 0)),
    w: clamp(b * 0.7 + (rnd() - 0.5) * 0.3),
  }))
  const frames = [], tl = { t: [], fatigue: [], withdrawal: [], risk: [], n_persons: [] }
  for (let k = 0; k < FPS * DUR; k++) {
    const t = +(k / FPS).toFixed(2)
    const persons = []
    for (const p of people) {
      const gy = p.onSlab ? 6 : 0
      let x = p.x0 + p.vx * t, z = p.z0 + p.vz * t
      if (p.onSlab) { x = 2.5 + Math.sin(t * 0.4) * 1.2; z = 4.8 + Math.sin(t * 0.25) * 0.6 }
      const droop = p.f * 0.25, phase = t * 4 + p.id
      const kp3 = T.map(([a, bb, c], j) => {
        let yy = bb, zz = c, xx = a
        if (j <= 4) { zz += droop * 0.6; yy -= droop * 0.4 }
        if (j >= 13) zz += Math.sin(phase + (j % 2) * Math.PI) * 0.18 * (1 - p.f)
        if (j === 9 || j === 10) zz += Math.sin(phase + (j % 2) * Math.PI) * 0.15
        return [+(xx + x).toFixed(3), +(yy + gy).toFixed(3), +(zz + z).toFixed(3)]
      })
      const kpts = kp3.map((q) => { const [u, w] = project(q); return [+u.toFixed(1), +w.toFixed(1), 0.9] })
      const xs = kpts.map((q) => q[0]), ys = kpts.map((q) => q[1])
      const fat = clamp(p.f + Math.sin(t * 0.7 + p.id) * 0.08 + t * 0.006)
      const wd = clamp(p.w + Math.cos(t * 0.5 + p.id) * 0.06)
      const near = p.onSlab && Math.abs(z - 4) < 0.9
      const risk = clamp(0.45 * fat + 0.2 * wd + (p.onSlab ? 0.35 : 0) + (near ? 0.15 : 0))
      persons.push({
        track_id: p.id,
        bbox: [Math.min(...xs) - 12, Math.min(...ys) - 18, Math.max(...xs) + 12, Math.max(...ys) + 8].map((q) => +q.toFixed(1)),
        kpts, kpts3d: kp3, fatigue: +fat.toFixed(3), withdrawal: +wd.toFixed(3),
        posture: fat > 0.6 ? "stooped" : "upright", height_m: gy, near_edge: near, risk: +risk.toFixed(3),
      })
    }
    frames.push({ t, persons })
    const avg = (key) => +(persons.reduce((s, q) => s + q[key], 0) / persons.length).toFixed(3)
    tl.t.push(t); tl.fatigue.push(avg("fatigue")); tl.withdrawal.push(avg("withdrawal"))
    tl.risk.push(+Math.max(...persons.map((q) => q.risk)).toFixed(3)); tl.n_persons.push(persons.length)
  }
  const workers = people.map((p) => {
    const hr = p.onSlab ? 0.85 : clamp(rnd() * 0.25)
    const overall = clamp(0.4 * p.f + 0.25 * p.w + 0.35 * hr)
    const flags = []
    if (p.f > 0.55) flags.push("head drooping", "slow movement")
    if (p.w > 0.5) flags.push("isolated from crew")
    if (p.onSlab) flags.push("working near drop edge")
    return { track_id: p.id, fatigue: +p.f.toFixed(2), withdrawal: +p.w.toFixed(2), height_risk: +hr.toFixed(2), overall: +overall.toFixed(2), status: statusOf(overall), flags }
  })
  const m = (k) => +(workers.reduce((s, w) => s + w[k], 0) / workers.length).toFixed(2)
  const overall = Math.max(...workers.map((w) => w.overall))
  const summary = {
    n_workers: workers.length, fatigue: m("fatigue"), withdrawal: m("withdrawal"), height_risk: Math.max(...workers.map((w) => w.height_risk)),
    overall: +overall.toFixed(2), status: v.status, predicted_class: v.class_name ?? "safe_general",
    predicted_unsafe_prob: +clamp(overall + 0.05).toFixed(2), headline: headlines[v.status],
  }
  const dir = path.join(root, v.id)
  fs.mkdirSync(dir, { recursive: true })
  const meta = { id: v.id, source: v.source, label: v.label, class_name: v.class_name, split: v.label === null ? null : v.id.includes("te") ? "test" : "train", fps: 30, width: W, height: H, n_frames: DUR * 30, duration: DUR }
  fs.writeFileSync(path.join(dir, "video.json"), JSON.stringify({ meta, analysis: { id: v.id, fps: FPS, frames, workers, summary, timeline: tl } }))

  // thumbnail svg
  const hue = { green: "#22d3ee", amber: "#f59e0b", red: "#ef4444" }[v.status]
  fs.writeFileSync(path.join(dir, "thumb.svg"), `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1626"/><stop offset="1" stop-color="#1b2a3f"/></linearGradient></defs><rect width="320" height="180" fill="url(#g)"/><path d="M0 140 L320 120 L320 180 L0 180Z" fill="#26364d"/><rect x="190" y="40" width="110" height="10" fill="#3b4b63"/><g stroke="#41536d">${Array.from({ length: 8 }, (_, i) => `<line x1="${195 + i * 14}" y1="50" x2="${195 + i * 14}" y2="130"/>`).join("")}</g>${people.map((p, i) => `<g stroke="${hue}" stroke-width="2.5" stroke-linecap="round" fill="none"><circle cx="${60 + i * 50}" cy="88" r="6"/><path d="M${60 + i * 50} 94 v26 m0 -20 l-10 10 m10 -10 l10 10 m-10 10 l-8 16 m8 -16 l8 16"/></g>`).join("")}</svg>`)

  // scene point cloud: ground + raised slab with edge + back wall
  const pts = []
  const push = (x, y, z, r, g, bl) => pts.push(x, y, z, r, g, bl)
  for (let i = 0; i < 60000; i++) { const x = -10 + rnd() * 20, z = -4 + rnd() * 16; const n = rnd() * 0.08; push(x, n * 0.3, z, 0.42 + n, 0.38 + n, 0.32 + n) }
  for (let i = 0; i < 25000; i++) { const x = 0 + rnd() * 9, z = 4 + rnd() * 6; const n = rnd() * 0.1; push(x, 6 + n * 0.1, z, 0.55 + n, 0.55 + n, 0.58 + n) }
  for (let i = 0; i < 20000; i++) { const x = rnd() * 9, y = rnd() * 6, z = 4 + rnd() * 6; if (rnd() < 0.5) push(x, y, 4 + (rnd() < 0.08 ? 0 : 6 * Math.floor(rnd() * 2)), 0.35, 0.4, 0.48); else push(Math.floor(rnd() * 4) * 3, y, z, 0.6, 0.45, 0.2) }
  for (let i = 0; i < 30000; i++) { const x = -10 + rnd() * 20, y = rnd() * 12, n = rnd() * 0.1; push(x, y, 12 + n, 0.3 + n, 0.33 + n, 0.4 + n) }
  const buf = Buffer.from(new Float32Array(pts).buffer)
  fs.writeFileSync(path.join(dir, "scene_points.bin"), buf)
  fs.writeFileSync(path.join(dir, "scene.json"), JSON.stringify({
    points: "scene_points.bin", n_points: pts.length / 6, bounds: { min: [-10, 0, -4], max: [10, 12, 12.1] }, ground_y: 0,
    edges: [{ polyline: [[0, 6, 4], [9, 6, 4]], drop_m: 6.0 }, { polyline: [[0, 6, 4], [0, 6, 10]], drop_m: 6.0 }],
    camera: { fov: 60, position: [0, 1.5, -9] },
  }))
  index.push({ id: v.id, source: v.source, label: v.label, class_name: v.class_name, thumb: `/mock/${v.id}/thumb.svg`, summary })
}
fs.writeFileSync(path.join(root, "index.json"), JSON.stringify(index, null, 1))

const classes = ["safe_walkway", "safe_ppe", "unsafe_fatigue", "unsafe_no_helmet", "unsafe_height_no_harness", "unsafe_ladder", "unsafe_machinery", "unsafe_lifting"]
fs.writeFileSync(path.join(root, "model.json"), JSON.stringify({
  model: "GradientBoosting (mock)", accuracy: 0.81, f1_macro: 0.77, n_train: 52, n_test: 19, classes,
  confusion_matrix: classes.map((_, i) => classes.map((_, j) => (i === j ? 2 + Math.floor(rnd() * 3) : rnd() < 0.15 ? 1 : 0))),
  feature_importances: { head_pitch_mean: 0.18, motion_energy: 0.15, height_max: 0.14, near_edge_frac: 0.12, isolation_dist: 0.1, stoop_frac: 0.09, wrist_speed: 0.08, n_persons: 0.06, arms_overhead_frac: 0.05, kpt_conf_mean: 0.03 },
}, null, 1))
console.log("mock written to", root)
