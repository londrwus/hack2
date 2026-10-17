import { useEffect, useState } from "react"
import { api, type ModelMetrics } from "@/lib/api"
import { SectionCard, StatCard, StatusPill, StackedBar, Legend, dataColors } from "@/components/kit"

const num = (v: unknown) => (typeof v === "number" ? v : undefined)
const pretty = (s: string) => s === "0" ? "Safe" : s === "1" ? "Unsafe" : s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())

export default function ModelPage() {
  const [m, setM] = useState<ModelMetrics>()
  const [err, setErr] = useState<string>()
  useEffect(() => { api.model().then(setM).catch((e) => setErr(String(e))) }, [])
  if (err) return <div className="text-sm text-risk">{err}</div>
  if (!m) return <div className="text-sm text-muted-foreground">Loading model…</div>

  const fi = Array.isArray(m.feature_importances)
    ? m.feature_importances.map((x) => ({ name: x.name, v: x.importance }))
    : Object.entries(m.feature_importances ?? {}).map(([name, v]) => ({ name, v: Number(v) }))
  fi.sort((a, b) => b.v - a.v)
  const top = fi.slice(0, 12)
  const maxV = Math.max(1e-9, ...top.map((x) => x.v))
  const cm = m.confusion_matrix ?? []
  const classes = m.classes ?? cm.map((_, i) => String(i))
  const maxCell = Math.max(1, ...cm.flat())
  const acc = num(m.accuracy) ?? num(m.test_accuracy)
  const f1 = num(m.f1_macro) ?? num(m.f1)
  const total = cm.flat().reduce((a, b) => a + b, 0)
  const correct = cm.reduce((a, r, i) => a + (r[i] ?? 0), 0)
  const isUnsafe = (i: number) => { const c = classes[i] ?? ""; return c === "1" || c.startsWith("unsafe") }
  const multi = classes.length > 2
  let wrongType = 0
  cm.forEach((r, i) => r.forEach((v, j) => { if (multi && i !== j && isUnsafe(i) === isUnsafe(j)) wrongType += v }))
  const segs = [
    { label: "Exact class", value: correct, color: dataColors.teal },
    { label: "Right safety call, wrong type", value: wrongType, color: dataColors.amber },
    { label: "Safe and unsafe confused", value: Math.max(0, total - correct - wrongType), color: dataColors.pink },
  ]
  const support = cm.map((r) => r.reduce((a, b) => a + b, 0))
  const cols = Object.values(dataColors)
  const supSegs = classes.map((c, i) => ({ label: pretty(c), value: support[i] ?? 0, color: cols[i % cols.length] }))

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Risk model</h1>
          <p className="mt-1 text-sm text-muted-foreground">Classifier that turns pose, motion and height features into a site-risk class per clip.</p>
        </div>
        {m.model && <StatusPill tone="ok">{String(m.model)}</StatusPill>}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Accuracy" tone="ok" value={acc !== undefined ? (acc * 100).toFixed(1) : "—"} unit={acc !== undefined ? "%" : undefined} sub="Held-out clips" />
        <StatCard label="Macro F1" value={f1 !== undefined ? f1.toFixed(2) : "—"} sub={`Across ${classes.length} classes`} />
        <StatCard label="Train clips" value={num(m.n_train) ?? "—"} sub="Labelled site footage" />
        <StatCard label={m.n_test ? "Test clips" : "Evaluation"} value={m.n_test ? (num(m.n_test) ?? "—") : "3-fold"} sub={m.n_test ? "Never seen in training" : "Cross-validation"} />
      </div>
      {total > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <SectionCard title="Where predictions land" footer={`${correct} of ${total} test clips classified exactly`}>
            <div className="text-[28px] font-semibold tabular-nums text-ink">{Math.round((correct / total) * 100)}%<span className="ml-2 text-sm font-normal text-muted-foreground">exact match</span></div>
            <StackedBar segments={multi ? segs : segs.filter((x) => x.label !== "Right safety call, wrong type")} height={12} className="my-4" />
            <Legend segments={multi ? segs : segs.filter((x) => x.label !== "Right safety call, wrong type")} />
          </SectionCard>
          <SectionCard title={m.n_test ? "Test clips per class" : "Clips per class"} footer={`${classes.length} classes`}>
            <StackedBar segments={supSegs} height={12} className="mb-3" />
            <Legend segments={supSegs} />
          </SectionCard>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Confusion matrix" footer="Rows: true class · columns: predicted">
          {cm.length ? (
            <div className="overflow-x-auto">
              <table className="border-separate border-spacing-[3px] text-xs">
                <thead><tr><th />{classes.map((_, i) => <th key={i} className="w-9 pb-1 text-center font-normal tabular-nums text-muted-foreground">{i + 1}</th>)}</tr></thead>
                <tbody>
                  {cm.map((row, i) => (
                    <tr key={i}>
                      <td className="max-w-44 truncate pr-3 text-right text-muted-foreground"><span className="mr-1.5 tabular-nums">{i + 1}</span>{pretty(classes[i] ?? "")}</td>
                      {row.map((v, j) => {
                        const a = v / maxCell
                        const bg = !v ? "#F6F6F5" : i === j ? `rgba(24,181,165,${0.18 + a * 0.75})` : `rgba(236,72,153,${0.15 + a * 0.6})`
                        return <td key={j} className="size-9 rounded-[8px] text-center tabular-nums" style={{ background: bg, color: v && a > 0.6 ? "#fff" : "#1F1F1F" }}>{v || ""}</td>
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="text-sm text-muted-foreground">No confusion matrix reported.</div>}
        </SectionCard>
        <SectionCard title="What the model looks at" footer="Relative importance, top features">
          <div className="space-y-2.5">
            {top.map((x, i) => (
              <div key={x.name} className="flex items-center gap-3 text-sm">
                <span className="w-44 truncate text-ink">{pretty(x.name)}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-subtle"><div className="h-full rounded-full" style={{ width: `${(x.v / maxV) * 100}%`, background: i < 3 ? "#1F1F1F" : "#C9C9C4" }} /></div>
                <span className="w-12 text-right tabular-nums text-muted-foreground">{x.v.toFixed(3)}</span>
              </div>
            ))}
            {!top.length && <div className="text-sm text-muted-foreground">No feature importances reported.</div>}
          </div>
        </SectionCard>
      </div>
      <p className="text-xs text-muted-foreground">Trained on 71 labelled safe/unsafe site clips. Scores are conversation prompts for supervisors, not diagnoses.</p>
    </div>
  )
}
