import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { UploadCloud, Loader2, Check, XCircle, Film } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CloudHero, SectionCard, RingProgress, StatusPill } from "@/components/kit"
import { cn } from "@/lib/utils"

const STEPS = ["Uploading", "Detecting workers (YOLO)", "Tracking pose", "Estimating depth", "Building 3D twin", "Scoring wellbeing signals"]
const INFO = [
  ["What we look for", "Slowed movement, stooped posture and time spent near unprotected edges."],
  ["What you get", "A per-worker readiness score, flagged moments and a 3D twin of the site."],
  ["What it is not", "A diagnosis. Scores are prompts for a supervisor check-in."],
]

export default function UploadPage() {
  const nav = useNavigate()
  const [drag, setDrag] = useState(false)
  const [file, setFile] = useState<File>()
  const [status, setStatus] = useState<string>()
  const [error, setError] = useState<string>()
  const [prog, setProg] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  async function run(f: File) {
    setFile(f); setError(undefined); setStatus("uploading"); setProg(3)
    try {
      const fd = new FormData()
      fd.append("file", f)
      const r = await fetch("/api/analyze", { method: "POST", body: fd })
      if (!r.ok) throw new Error(`Upload failed (${r.status}). Is the backend running on :8000?`)
      const { id } = await r.json()
      const t0 = Date.now()
      for (;;) {
        await new Promise((res) => setTimeout(res, 2000))
        const j = await fetch(`/api/jobs/${id}`).then((x) => x.json())
        const st = String(j.status ?? "running")
        setStatus(st)
        setProg((p) => Math.min(95, Math.max(p, typeof j.progress === "number" ? j.progress * 100 : 5 + (Date.now() - t0) / 1500)))
        if (["done", "complete", "completed", "finished", "success"].includes(st)) { setProg(100); setTimeout(() => nav(`/video/${encodeURIComponent(j.id ?? id)}`), 600); return }
        if (["error", "failed"].includes(st)) throw new Error(j.error ?? "Pipeline failed")
      }
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); setStatus(undefined) }
  }

  const step = Math.min(STEPS.length - 1, Math.floor((prog / 100) * STEPS.length))
  const done = prog >= 100
  return (
    <div className="mx-auto max-w-[880px] space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">Analyse footage</h1>
        <p className="mt-1 text-sm text-muted-foreground">Upload a site clip. Detection, pose, depth and the 3D twin run on GPU, then each worker gets a readiness score.</p>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) run(f) }}
        onClick={() => !status && input.current?.click()}
        className={cn("cursor-pointer rounded-[20px] border bg-white p-2 shadow-soft transition", drag ? "border-ink" : "border-hairline")}
      >
        <input ref={input} type="file" accept="video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f) }} />
        <CloudHero className="min-h-64" icon={status ? <Loader2 className="animate-spin" /> : <UploadCloud />} />
        <div className="flex flex-wrap items-center gap-3 px-4 pt-5 pb-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[15px] font-medium text-ink">{file ? file.name : "Drop a video here, or browse"}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB` : "MP4 or MOV, up to 2 minutes. Footage stays on this server."}</div>
          </div>
          {!status && <Button variant="ghost" onClick={(e) => { e.stopPropagation(); nav("/") }}>Skip</Button>}
          <Button variant="primary" disabled={!!status}><Film className="size-4" strokeWidth={1.5} />Choose file</Button>
        </div>
      </div>

      {status && (
        <SectionCard title="Pipeline" menu={false} action={<RingProgress value={done ? STEPS.length : step} total={STEPS.length} />}
          footer={<>Job status: <span className="text-ink">{status}</span></>} footerAction={<span className="text-xs tabular-nums text-ink">{Math.round(prog)}%</span>}>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-subtle"><div className="h-full rounded-full bg-ink transition-all" style={{ width: `${prog}%` }} /></div>
          <ol className="divide-y divide-hairline">
            {STEPS.map((s, i) => {
              const st = done || i < step ? "done" : i === step ? "now" : "todo"
              return (
                <li key={s} className="flex items-center gap-3 py-2.5 text-sm">
                  <span className={cn("grid size-5 place-items-center rounded-full border", st === "done" ? "border-ink bg-ink text-white" : "border-hairline text-muted-foreground")}>
                    {st === "done" ? <Check className="size-3" strokeWidth={2.5} /> : st === "now" ? <Loader2 className="size-3 animate-spin" /> : <span className="text-[10px] tabular-nums">{i + 1}</span>}
                  </span>
                  <span className={cn("flex-1", st === "todo" ? "text-muted-foreground" : "text-ink")}>{s}</span>
                  {st === "now" && <StatusPill tone="warn">Running</StatusPill>}
                  {st === "done" && <span className="text-xs text-muted-foreground">Done</span>}
                </li>
              )
            })}
          </ol>
        </SectionCard>
      )}
      {error && (
        <div className="flex items-center gap-3 rounded-[16px] border border-hairline bg-white p-4 text-sm shadow-soft">
          <XCircle className="size-5 text-risk" strokeWidth={1.5} /><span className="flex-1 text-ink">{error}</span>
          <Button size="sm" variant="secondary" onClick={() => file && run(file)}>Retry</Button>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        {INFO.map(([t, d]) => (
          <div key={t} className="rounded-[16px] border border-hairline bg-white p-4 shadow-soft">
            <div className="text-sm font-medium text-ink">{t}</div>
            <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{d}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
