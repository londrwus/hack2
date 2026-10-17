import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { motion } from "framer-motion"
import { ArrowLeft, Pause, Play, HeartHandshake, Phone, ShieldAlert, ShieldCheck, Box, Film } from "lucide-react"
import { Area, AreaChart, CartesianGrid, Line, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { api, media, frameAt, COCO_EDGES, riskColor, statusOf, type Analysis, type Meta, type Scene } from "@/lib/api"
import { SectionCard, StatusPill, HalftoneAccent, Chip, dataColors, toneColor, type Tone } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Slider } from "@/components/ui/slider"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import Twin from "@/components/Twin"
import { cn } from "@/lib/utils"

type Src = "annotated" | "raw" | "depth"

function useClock(duration: number, videoRef: React.RefObject<HTMLVideoElement | null>, videoOk: boolean) {
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(true)
  const last = useRef(performance.now())
  const tRef = useRef(0)
  useEffect(() => {
    let raf = 0
    const tick = (now: number) => {
      const dt = (now - last.current) / 1000
      last.current = now
      const v = videoRef.current
      if (videoOk && v && v.readyState >= 2) {
        tRef.current = v.currentTime
      } else if (playing) {
        tRef.current = (tRef.current + dt) % Math.max(duration, 0.1)
      }
      setT(tRef.current)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [duration, playing, videoOk, videoRef])
  useEffect(() => {
    const v = videoRef.current
    if (!v || !videoOk) return
    if (playing) v.play().catch(() => {})
    else v.pause()
  }, [playing, videoOk, videoRef])
  const seek = useCallback((s: number) => {
    tRef.current = s
    const v = videoRef.current
    if (v && videoOk) v.currentTime = s
    setT(s)
  }, [videoOk, videoRef])
  return { t, playing, setPlaying, seek }
}

export default function Detail() {
  const { id = "" } = useParams()
  const [data, setData] = useState<{ meta: Meta; analysis: Analysis }>()
  const [scene, setScene] = useState<Scene | null>()
  const [err, setErr] = useState<string>()
  const [src, setSrc] = useState<Src>("annotated")
  const [overlay, setOverlay] = useState(true)
  const [videoOk, setVideoOk] = useState(true)
  const [tab, setTab] = useState<string>("analysis")
  const [focus, setFocus] = useState<number | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.video(id).then(setData).catch((e) => setErr(String(e)))
    api.scene(id).then(setScene).catch(() => setScene(null))
  }, [id])

  const a = data?.analysis
  const duration = data?.meta.duration || (a ? a.timeline.t[a.timeline.t.length - 1] ?? 10 : 10)
  const { t, playing, setPlaying, seek } = useClock(duration, videoRef, videoOk)
  const frame = useMemo(() => (a ? frameAt(a.frames, t) : undefined), [a, t])

  if (err) return <div className="text-sm text-[var(--risk)]">Could not load {id}: {err}</div>
  if (!data || !a) return <div className="animate-pulse text-sm text-muted-foreground">Loading analysis…</div>
  const { meta } = data
  const s = a.summary
  const fitHeight = s.height_risk < 0.5 && s.overall < 0.6
  const videoUrl = src === "raw" ? rawUrl(meta) : media(id, `${src}.mp4`)
  const showOverlay = !videoOk || (overlay && src !== "annotated")
  const tone = (st: string): Tone => (st === "red" ? "risk" : st === "amber" ? "warn" : "ok")

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/"><Button variant="secondary" size="sm"><ArrowLeft className="size-4" strokeWidth={1.5} />Site</Button></Link>
        <h1 className="tnum text-xl font-semibold tracking-tight text-ink">{id}</h1>
        <StatusPill tone={tone(s.status)}>{s.status === "red" ? "High risk" : s.status === "amber" ? "Watch" : "OK"}</StatusPill>
        <span className="text-sm text-muted-foreground">{s.headline}</span>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList>
          <TabsTrigger value="analysis"><Film className="size-4" strokeWidth={1.5} />Analysis</TabsTrigger>
          <TabsTrigger value="twin"><Box className="size-4" strokeWidth={1.5} />3D digital twin</TabsTrigger>
        </TabsList>

        <TabsContent value="analysis" className="mt-4">
          <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
            <div className="min-w-0 space-y-4">
              <section className="overflow-hidden rounded-[18px] border border-hairline bg-white p-2 shadow-soft">
                <div ref={boxRef} className="relative w-full overflow-hidden rounded-[12px] bg-[#1F1F1F]" style={{ aspectRatio: `${meta.width}/${meta.height}` }}>
                  {videoOk ? (
                    <video
                      key={videoUrl} ref={videoRef} src={videoUrl} muted loop playsInline autoPlay
                      className="absolute inset-0 size-full object-contain"
                      onError={() => { if (src !== "annotated") setSrc("annotated"); else setVideoOk(false) }}
                    />
                  ) : (
                    <div className="absolute inset-0 bg-[#F7F7F6]">
                      <div className="absolute left-3 top-3 rounded-full border border-hairline bg-white px-2.5 py-1 text-[11px] text-muted-foreground">Video unavailable, skeleton replay</div>
                    </div>
                  )}
                  {showOverlay && <Overlay meta={meta} frame={frame} focus={focus} boxRef={boxRef} videoRef={videoRef} videoOk={videoOk} />}
                  <div className="tnum pointer-events-none absolute right-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-xs font-medium text-ink shadow-soft">
                    {t.toFixed(1)}s · {frame?.persons.length ?? 0} in frame
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3 px-2 pb-1 pt-3">
                  <Button size="icon" variant="primary" aria-label={playing ? "Pause" : "Play"} onClick={() => setPlaying(!playing)}>{playing ? <Pause strokeWidth={1.5} /> : <Play strokeWidth={1.5} />}</Button>
                  <span className="tnum w-20 text-xs text-muted-foreground">{t.toFixed(1)} / {duration.toFixed(1)}s</span>
                  <Slider className="min-w-40 flex-1" min={0} max={duration} step={0.05} value={[t]} onValueChange={(v) => seek(Array.isArray(v) ? v[0] : v)} />
                  <div className="flex rounded-[10px] bg-subtle p-0.5">
                    {(["annotated", "raw", "depth"] as Src[]).map((k) => (
                      <button key={k} onClick={() => { setSrc(k); setVideoOk(true) }}
                        className={cn("h-7 rounded-[8px] border px-3 text-xs font-medium capitalize transition", src === k ? "border-hairline bg-white text-ink shadow-soft" : "border-transparent text-muted-foreground hover:text-ink")}>{k}</button>
                    ))}
                  </div>
                  <Button size="sm" variant={overlay && src !== "annotated" ? "secondary" : "ghost"} disabled={src === "annotated"} title={src === "annotated" ? "Skeleton is baked into the annotated video" : "Toggle live skeleton overlay"} onClick={() => setOverlay(!overlay)}>Skeleton</Button>
                </div>
              </section>
              <Timelines a={a} t={t} seek={seek} />
            </div>

            <div className="space-y-4">
              <Verdict fit={fitHeight} s={s} />
              <SectionCard title="Workers" action={<span className="tnum text-xs text-muted-foreground">{a.workers.length} tracked</span>} bodyClassName="px-3 pb-3">
                <ScrollArea className="h-[420px] pr-2">
                  <div className="space-y-2">
                    {a.workers.map((w) => {
                      const live = frame?.persons.find((p) => p.track_id === w.track_id)
                      const segs = [
                        { label: "Fatigue", value: live?.fatigue ?? w.fatigue, color: dataColors.amber },
                        { label: "Withdrawal", value: live?.withdrawal ?? w.withdrawal, color: dataColors.sky },
                        { label: "Height", value: w.height_risk, color: dataColors.orange },
                      ]
                      return (
                        <motion.div key={w.track_id} layout onMouseEnter={() => setFocus(w.track_id)} onMouseLeave={() => setFocus(null)}
                          className={cn("rounded-[14px] border border-hairline bg-white p-3 transition hover:bg-[#FAFAF9]", focus === w.track_id && "border-[#D6D6D3]")}>
                          <div className="flex items-center gap-2.5">
                            <div className="tnum grid size-8 place-items-center rounded-full bg-subtle text-xs font-semibold text-ink">{w.track_id}</div>
                            <div className="flex-1 leading-tight">
                              <div className="text-sm font-medium text-ink">Worker {w.track_id}</div>
                              <div className="text-xs text-muted-foreground">{live ? `${live.posture} · ${live.height_m.toFixed(1)} m` : "Not in frame"}</div>
                            </div>
                            <StatusPill tone={tone(w.status)}>{w.status === "red" ? "Risk" : w.status === "amber" ? "Watch" : "OK"}</StatusPill>
                          </div>
                          <div className="mt-3 space-y-1.5">
                            {segs.map((g) => (
                              <div key={g.label} className="flex items-center gap-2 text-xs">
                                <span className="w-16 text-muted-foreground">{g.label}</span>
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle"><div className="h-full rounded-full" style={{ width: `${Math.round(g.value * 100)}%`, background: g.color }} /></div>
                                <span className="tnum w-8 text-right text-ink">{Math.round(g.value * 100)}</span>
                              </div>
                            ))}
                          </div>
                          {w.flags.length > 0 && (
                            <div className="mt-2.5 flex flex-wrap gap-1">
                              {w.flags.map((f) => <span key={f} className="rounded-full bg-subtle px-2 py-0.5 text-[11px] text-ink">{f}</span>)}
                            </div>
                          )}
                        </motion.div>
                      )
                    })}
                  </div>
                </ScrollArea>
              </SectionCard>
              <Signpost />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="twin" className="mt-4">
          {tab === "twin" && (
            <Twin id={id} scene={scene} workers={a.workers} frames={a.frames} t={t} duration={duration} playing={playing} setPlaying={setPlaying} seek={seek} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

function rawUrl(meta: Meta) {
  const src = meta.source || ""
  if (/^(https?:)?\//.test(src)) return src
  const dir = src === "safe_unsafe" ? "safe_unsafe/data" : src === "extra" ? "extra/raw" : src || "uploads"
  return `/media/raw/${dir}/${meta.id}.mp4`
}

const KCONF = 0.35
const okK = (k?: number[]) => !!k && k[2] >= KCONF && (k[0] > 1 || k[1] > 1)

function Overlay({ meta, frame, focus, boxRef, videoRef, videoOk }: {
  meta: Meta; frame?: ReturnType<typeof frameAt>; focus: number | null
  boxRef: React.RefObject<HTMLDivElement | null>; videoRef: React.RefObject<HTMLVideoElement | null>; videoOk: boolean
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setSize({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [boxRef])
  useEffect(() => {
    const cv = ref.current
    if (!cv || !size.w) return
    const dpr = window.devicePixelRatio || 1
    if (cv.width !== Math.round(size.w * dpr)) cv.width = Math.round(size.w * dpr)
    if (cv.height !== Math.round(size.h * dpr)) cv.height = Math.round(size.h * dpr)
    const g = cv.getContext("2d")!
    g.setTransform(1, 0, 0, 1, 0, 0)
    g.clearRect(0, 0, cv.width, cv.height)
    // displayed video rect under object-fit: contain
    const v = videoRef.current
    const vw = (videoOk && v?.videoWidth) || meta.width, vh = (videoOk && v?.videoHeight) || meta.height
    const fit = Math.min(size.w / vw, size.h / vh)
    const dw = vw * fit, dh = vh * fit
    const ox = (size.w - dw) / 2, oy = (size.h - dh) / 2
    const sx = dw / meta.width, sy = dh / meta.height
    g.setTransform(dpr * sx, 0, 0, dpr * sy, dpr * ox, dpr * oy)
    const sc = 1 / sx // keep stroke widths in CSS px
    for (const p of frame?.persons ?? []) {
      const c = riskColor(p.risk)
      g.globalAlpha = focus !== null && focus !== p.track_id ? 0.25 : 1
      g.shadowBlur = 0
      g.strokeStyle = c; g.lineWidth = 2.5 * sc; g.lineCap = "round"
      for (const [i, j] of COCO_EDGES) {
        const A = p.kpts[i], B = p.kpts[j]
        if (!okK(A) || !okK(B)) continue
        g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke()
      }
      g.fillStyle = "#fff"
      for (const k of p.kpts) if (okK(k)) { g.beginPath(); g.arc(k[0], k[1], 2.5 * sc, 0, 7); g.fill() }
      const [x1, y1, x2, y2] = p.bbox
      g.shadowBlur = 0; g.lineWidth = 1.2 * sc; g.setLineDash([6 * sc, 4 * sc]); g.strokeRect(x1, y1, x2 - x1, y2 - y1); g.setLineDash([])
      const label = `#${p.track_id} ${Math.round(p.risk * 100)}%${p.near_edge ? " EDGE" : ""}`
      g.font = `600 ${12 * sc}px Inter, sans-serif`
      const w = g.measureText(label).width + 10 * sc
      g.fillStyle = c; g.fillRect(x1, y1 - 18 * sc, w, 18 * sc)
      g.fillStyle = "#fff"; g.fillText(label, x1 + 5 * sc, y1 - 5 * sc)
    }
    g.globalAlpha = 1
  }, [frame, meta, focus, size, videoRef, videoOk])
  return <canvas ref={ref} className="pointer-events-none absolute inset-0 size-full" />
}

const AX = { fill: "#8A8A85", fontSize: 11 }
function Timelines({ a, t, seek }: { a: Analysis; t: number; seek: (s: number) => void }) {
  const rows = useMemo(() => a.timeline.t.map((x, i) => ({ t: x, fatigue: a.timeline.fatigue[i], withdrawal: a.timeline.withdrawal[i], risk: a.timeline.risk[i], n: a.timeline.n_persons[i] })), [a])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onClick = (e: any) => { const v = e?.activeLabel ?? e?.activePayload?.[0]?.payload?.t; if (v !== undefined) seek(Number(v)) }
  const key = [["Fatigue", dataColors.amber], ["Withdrawal", dataColors.sky], ["Risk (max)", "#E5484D"]]
  return (
    <SectionCard title="Signals over time" action={<div className="hidden gap-4 text-xs text-muted-foreground sm:flex">{key.map(([l, c]) => <span key={l} className="flex items-center gap-1.5"><i className="size-2 rounded-full" style={{ background: c }} />{l}</span>)}</div>}
      footer="Click the chart to seek. Dashed line marks the 0.65 alert threshold.">
      <div className="h-56">
        <ResponsiveContainer>
          <ComposedChart data={rows} onClick={onClick} margin={{ left: -20, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="gr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#E5484D" stopOpacity={0.14} /><stop offset="1" stopColor="#E5484D" stopOpacity={0} /></linearGradient>
            </defs>
            <CartesianGrid stroke="#EFEFED" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={AX} axisLine={false} tickLine={false} tickFormatter={(v) => `${Math.round(v)}s`} />
            <YAxis domain={[0, 1]} tick={AX} axisLine={false} tickLine={false} />
            <RTooltip contentStyle={{ background: "#fff", border: "1px solid #E7E7E5", borderRadius: 10, fontSize: 12, boxShadow: "0 4px 16px rgba(0,0,0,.06)" }} formatter={(v) => Number(v).toFixed(2)} labelFormatter={(v) => `${Number(v).toFixed(1)}s`} />
            <Area type="monotone" dataKey="risk" stroke="#E5484D" fill="url(#gr)" strokeWidth={1.75} isAnimationActive={false} />
            <Line type="monotone" dataKey="fatigue" stroke={dataColors.amber} dot={false} strokeWidth={1.75} isAnimationActive={false} />
            <Line type="monotone" dataKey="withdrawal" stroke={dataColors.sky} dot={false} strokeWidth={1.75} isAnimationActive={false} />
            <ReferenceLine y={0.65} stroke="#E5484D" strokeDasharray="4 4" strokeOpacity={0.5} />
            <ReferenceLine x={t} stroke="#1F1F1F" strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <span className="w-24 shrink-0 text-xs text-muted-foreground">People in frame</span>
        <div className="h-10 flex-1">
          <ResponsiveContainer>
            <AreaChart data={rows} margin={{ left: 0, right: 8 }}>
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} hide />
              <YAxis hide />
              <Area type="step" dataKey="n" stroke={dataColors.teal} fill={dataColors.teal} fillOpacity={0.12} strokeWidth={1.5} isAnimationActive={false} />
              <ReferenceLine x={t} stroke="#1F1F1F" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </SectionCard>
  )
}

function Verdict({ fit, s }: { fit: boolean; s: Analysis["summary"] }) {
  const tone: Tone = fit ? "ok" : s.status === "red" ? "risk" : "warn"
  const c = toneColor[tone]
  const pct = Math.round(s.overall * 100)
  const rows: [string, React.ReactNode][] = [
    ["Predicted", s.predicted_class],
    ["Unsafe probability", <span style={{ color: riskColor(s.predicted_unsafe_prob) }}>{Math.round(s.predicted_unsafe_prob * 100)}%</span>],
    ["Height risk", <span className="capitalize">{statusOf(s.height_risk)}</span>],
    ["Workers", s.n_workers],
  ]
  return (
    <SectionCard title="Fit for height work" className="relative" footer={`Overall score ${pct} of 100`}>
      <HalftoneAccent corner="tr" />
      <div className="relative flex items-center gap-4">
        <div className="relative grid size-[72px] shrink-0 place-items-center">
          <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90">
            <circle cx="18" cy="18" r="16" fill="none" stroke="#EFEFED" strokeWidth="2.5" />
            <circle cx="18" cy="18" r="16" fill="none" stroke={c} strokeWidth="2.5" strokeLinecap="round" strokeDasharray={`${s.overall * 100.5} 100.5`} />
          </svg>
          <span className="tnum text-lg font-semibold text-ink">{pct}</span>
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-ink">
            {fit ? <ShieldCheck className="size-5" strokeWidth={1.75} style={{ color: c }} /> : <ShieldAlert className="size-5" strokeWidth={1.75} style={{ color: c }} />}
            {fit ? "Yes" : s.status === "red" ? "Not now" : "Check first"}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {fit ? "No strong fatigue or edge-risk signals. Normal controls apply." : "Talk to the crew before work at height. Consider a break, buddy-up or ground-level task."}
          </p>
        </div>
      </div>
      <div className="relative mt-4 divide-y divide-hairline border-t border-hairline">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center py-2 text-sm"><span className="flex-1 text-muted-foreground">{k}</span><span className="tnum font-medium text-ink">{v}</span></div>
        ))}
      </div>
    </SectionCard>
  )
}

function Signpost() {
  return (
    <SectionCard menu={false} className="relative">
      <div className="flex items-start gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-full border border-hairline bg-white shadow-soft"><HeartHandshake className="size-4 text-[var(--ok)]" strokeWidth={1.5} /></div>
        <div className="space-y-2.5">
          <p className="text-sm font-medium text-ink">Looking out for each other</p>
          <p className="text-xs leading-relaxed text-muted-foreground">These signals are prompts for a friendly chat, not a judgement. If someone is struggling, free confidential support is available 24/7.</p>
          <div className="flex flex-wrap gap-2">
            <a href="tel:03456051956" className="flex h-7 items-center gap-1.5 rounded-[8px] bg-subtle px-2.5 text-xs text-ink"><Phone className="size-3" strokeWidth={1.5} />Lighthouse Club <span className="tnum">0345 605 1956</span></a>
            <a href="tel:116123" className="flex h-7 items-center gap-1.5 rounded-[8px] bg-subtle px-2.5 text-xs text-ink"><Phone className="size-3" strokeWidth={1.5} />Samaritans <span className="tnum">116 123</span></a>
          </div>
          <Dialog>
            <DialogTrigger render={<Chip />}>How to start the conversation</DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Starting a supportive check-in</DialogTitle>
                <DialogDescription>Simple, human steps. No blame.</DialogDescription>
              </DialogHeader>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                <li>Find a private moment, ideally over a brew, away from the crew.</li>
                <li>Ask twice: "How are you doing? No, really, how are you?"</li>
                <li>Listen, don't fix. Offer a break or a ground-level task today.</li>
                <li>If they mention feeling hopeless or unsafe, stay with them and call Samaritans 116 123 or the Lighthouse Club helpline 0345 605 1956 together. In an emergency, call 999.</li>
              </ul>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </SectionCard>
  )
}
