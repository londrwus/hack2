import { useEffect, useMemo, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { Search, Users, ArrowUpRight } from "lucide-react"
import { api, thumbUrl, type IndexItem, type Status } from "@/lib/api"
import { SectionCard, StatCard, StatusPill, StackedBar, Legend, Chip, toneColor, type Tone } from "@/components/kit"
import { cn } from "@/lib/utils"

const TONE: Record<Status, Tone> = { green: "ok", amber: "warn", red: "risk" }
const LABEL: Record<Status, string> = { green: "Fit", amber: "Check-in", red: "Hold" }
const pct = (v?: number) => Math.round((v ?? 0) * 100)

export default function Overview() {
  const [items, setItems] = useState<IndexItem[]>([])
  const [err, setErr] = useState<string>()
  const [filter, setFilter] = useState<Status | "all">("all")
  const [source, setSource] = useState("all")
  const [q, setQ] = useState("")
  const clipsOnly = useLocation().pathname === "/clips"

  useEffect(() => { api.videos().then(setItems).catch((e) => setErr(String(e))) }, [])

  const k = useMemo(() => {
    const c = { green: 0, amber: 0, red: 0 }
    let workers = 0, fat = 0
    for (const it of items) { c[it.summary?.status ?? "green"]++; workers += it.summary?.n_workers ?? 0; fat += it.summary?.fatigue ?? 0 }
    return { ...c, workers, fat: items.length ? fat / items.length : 0 }
  }, [items])
  const sources = useMemo(() => ["all", ...new Set(items.map((i) => i.source))], [items])
  const shown = items
    .filter((i) => filter === "all" || i.summary?.status === filter)
    .filter((i) => source === "all" || i.source === source)
    .filter((i) => !q || (i.id + (i.class_name ?? "") + (i.summary?.headline ?? "")).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (b.summary?.overall ?? 0) - (a.summary?.overall ?? 0))
  const attention = items.filter((i) => i.summary?.status !== "green").sort((a, b) => (b.summary?.overall ?? 0) - (a.summary?.overall ?? 0)).slice(0, 5)
  const segs = [
    { label: "Fit for height work", value: k.green, color: toneColor.ok },
    { label: "Check-in suggested", value: k.amber, color: toneColor.warn },
    { label: "Hold from height", value: k.red, color: toneColor.risk },
  ]

  const seg = "h-8 rounded-[8px] px-3 text-[13px] text-muted-foreground transition hover:text-ink"
  const segOn = "bg-white text-ink shadow-soft border border-hairline"

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">{clipsOnly ? "Clips" : "Site overview"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">Readiness for high-risk work, from site video. Here to support people, not to police them.</p>
        </div>
        <Link to="/upload" className="btn-dark inline-flex h-9 items-center rounded-[10px] px-3.5 text-sm font-medium">Analyse a clip</Link>
      </div>

      {!clipsOnly && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Workers scanned" value={k.workers} sub={`Across ${items.length} clips`} />
            <StatCard label="Fit for height work" tone="ok" value={k.green} unit="clips" sub={`${items.length ? Math.round((k.green / items.length) * 100) : 0}% of today's footage`} />
            <StatCard label="Needs a check-in" tone="warn" value={k.amber + k.red} unit="clips" sub={`${k.red} on hold from height`} />
            <StatCard label="Average fatigue" value={pct(k.fat)} unit="/ 100" sub="Index from posture and movement" />
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
            <SectionCard title="Readiness across clips" className="lg:col-span-2" footer={`${items.length} clips analysed`} footerAction={<Chip onClick={() => setFilter("red")}>Show holds</Chip>}>
              <div className="text-[28px] font-semibold tabular-nums text-ink">{items.length ? Math.round((k.green / items.length) * 100) : 0}%<span className="ml-2 text-sm font-normal text-muted-foreground">fit</span></div>
              <StackedBar segments={segs} className="mt-4" />
              <Legend segments={segs} className="mt-4" />
            </SectionCard>
            <SectionCard title="Who to check in with" className="lg:col-span-3" bodyClassName="px-2 pb-2">
              {attention.length === 0 && <p className="px-3 py-6 text-sm text-muted-foreground">Nobody flagged. Everyone looks ready.</p>}
              {attention.map((it) => (
                <Link key={it.id} to={`/video/${encodeURIComponent(it.id)}`} className="group flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-canvas">
                  <img src={thumbUrl(it)} alt="" className="h-9 w-14 shrink-0 rounded-md bg-subtle object-cover" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{it.summary?.headline}</div>
                    <div className="text-xs text-muted-foreground">{it.id} · {it.summary?.n_workers ?? 0} workers</div>
                  </div>
                  <span className="hidden text-xs tabular-nums text-muted-foreground sm:block">Fatigue {pct(it.summary?.fatigue)}</span>
                  <StatusPill tone={TONE[it.summary.status]}>{LABEL[it.summary.status]}</StatusPill>
                  <ArrowUpRight className="size-4 text-muted-foreground opacity-0 group-hover:opacity-100" strokeWidth={1.5} />
                </Link>
              ))}
            </SectionCard>
          </div>
        </>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-[10px] bg-subtle p-0.5">
          {(["all", "red", "amber", "green"] as const).map((s) => (
            <button key={s} onClick={() => setFilter(s)} className={cn(seg, "inline-flex items-center gap-1.5", filter === s && segOn)}>
              {s !== "all" && <span className="size-1.5 rounded-full" style={{ background: toneColor[TONE[s]] }} />}
              {s === "all" ? "All" : LABEL[s]}
            </button>
          ))}
        </div>
        <div className="flex rounded-[10px] bg-subtle p-0.5">
          {sources.map((s) => (
            <button key={s} onClick={() => setSource(s)} className={cn(seg, source === s && segOn)}>{s === "all" ? "All sources" : s}</button>
          ))}
        </div>
        <div className="ml-auto flex h-9 items-center gap-2 rounded-[10px] bg-subtle px-3">
          <Search className="size-4 text-muted-foreground" strokeWidth={1.5} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clips" className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
        </div>
      </div>

      {err && <div className="text-sm text-[#E5484D]">Failed to load: {err}</div>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {shown.map((it) => {
          const st = it.summary?.status ?? "green"
          return (
            <Link key={it.id} to={`/video/${encodeURIComponent(it.id)}`} className="group overflow-hidden rounded-[18px] border border-hairline bg-white shadow-soft transition hover:-translate-y-0.5">
              <div className="relative aspect-video overflow-hidden bg-subtle">
                <img src={thumbUrl(it)} alt="" className="size-full object-cover transition duration-500 group-hover:scale-[1.03]" onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0")} />
                <div className="absolute left-2.5 top-2.5"><StatusPill tone={TONE[st]} className="bg-white/95">{LABEL[st]}</StatusPill></div>
                <div className="absolute right-2.5 top-2.5 flex items-center gap-1 rounded-full bg-white/95 px-2 py-0.5 text-[11px] tabular-nums text-ink"><Users className="size-3" strokeWidth={1.5} />{it.summary?.n_workers ?? 0}</div>
              </div>
              <div className="space-y-3 p-4">
                <p className="line-clamp-2 min-h-[2.5rem] text-sm text-ink">{it.summary?.headline}</p>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  {([["Fatigue", it.summary?.fatigue], ["Withdrawal", it.summary?.withdrawal], ["Height", it.summary?.height_risk]] as const).map(([l, v]) => (
                    <div key={l}>
                      <div className="text-muted-foreground">{l}</div>
                      <div className="mt-0.5 tabular-nums text-ink">{pct(v)}</div>
                      <div className="mt-1 h-1 rounded-full bg-subtle"><div className="h-1 rounded-full" style={{ width: `${pct(v)}%`, background: toneColor[(v ?? 0) > 0.65 ? "risk" : (v ?? 0) > 0.4 ? "warn" : "ok"] }} /></div>
                    </div>
                  ))}
                </div>
                <div className="flex justify-between border-t border-hairline pt-3 text-xs text-muted-foreground">
                  <span className="truncate">{it.id}</span><span>{it.class_name ?? it.source}</span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
