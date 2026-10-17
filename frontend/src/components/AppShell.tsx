import OperatorDrawer from "@/components/kit/Operator"
import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"
import { LayoutGrid, Film, Box, Upload, Brain, LifeBuoy, PanelLeft, ChevronDown, Search, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { isMock, onMockChange } from "@/lib/api"
import { Input } from "@/components/ui/input"

type Item = { to: string; label: string; icon: typeof LayoutGrid; end?: boolean; count?: number }
const groups: { label: string; items: Item[] }[] = [
  { label: "Essentials", items: [
    { to: "/", label: "Overview", icon: LayoutGrid, end: true },
    { to: "/clips", label: "Clips", icon: Film },
    { to: "/twin", label: "3D twin", icon: Box },
  ] },
  { label: "Work", items: [
    { to: "/upload", label: "Analyse", icon: Upload },
    { to: "/model", label: "Model", icon: Brain },
  ] },
]

function NavItem({ item }: { item: Item }) {
  const Icon = item.icon
  return (
    <NavLink to={item.to} end={item.end} className={({ isActive }) => cn(
      "flex h-9 items-center gap-2.5 rounded-[10px] border px-2.5 text-sm transition-colors",
      isActive ? "border-hairline bg-white font-medium text-ink shadow-soft" : "border-transparent text-muted-foreground hover:text-ink")}>
      <Icon className="size-4" strokeWidth={1.5} />
      <span className="flex-1">{item.label}</span>
      {item.count != null && <span className="badge-glossy grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[11px] font-medium text-white tabular-nums">{item.count}</span>}
    </NavLink>
  )
}

function Group({ label, items }: { label: string; items: Item[] }) {
  const [open, setOpen] = useState(true)
  return (
    <div>
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center gap-1 px-2.5 pb-1.5 text-xs text-muted-foreground">
        {label}<ChevronDown className={cn("size-3 transition-transform", !open && "-rotate-90")} />
      </button>
      {open && <div className="space-y-0.5">{items.map(i => <NavItem key={i.to} item={i} />)}</div>}
    </div>
  )
}

export function Sidebar() {
  const [mock, setMock] = useState(isMock())
  useEffect(() => onMockChange(setMock), [])
  return (
    <aside className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col gap-5 px-3 py-4">
      <div className="flex items-center gap-2.5 px-1.5">
        <div className="grid size-7 place-items-center rounded-[8px] bg-ink text-xs font-semibold text-white">S</div>
        <div className="flex-1 leading-tight">
          <div className="text-sm font-semibold text-ink">SiteMind</div>
          <div className="text-[11px] text-muted-foreground">{mock ? "Demo data" : "Live site"}</div>
        </div>
        <PanelLeft className="size-4 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <Input placeholder="Search" kbd="/" icon={<Search />} />
      <nav className="flex flex-col gap-5">{groups.map(g => <Group key={g.label} {...g} />)}</nav>
      <div className="mt-auto space-y-2">
        <a href="https://www.lighthouseclub.org" target="_blank" rel="noreferrer" className="flex h-9 items-center gap-2.5 rounded-[10px] px-2.5 text-sm text-muted-foreground hover:text-ink">
          <LifeBuoy className="size-4" strokeWidth={1.5} />Help & support
        </a>
        <div className="flex items-center gap-2.5 rounded-[12px] border border-hairline bg-white p-2 shadow-soft">
          <div className="grid size-8 place-items-center rounded-full bg-subtle text-xs font-medium text-ink">SS</div>
          <div className="flex-1 leading-tight">
            <div className="text-sm font-medium text-ink">Site supervisor</div>
            <div className="text-[11px] text-muted-foreground">VAST London</div>
          </div>
          <ChevronsUpDown className="size-4 text-muted-foreground" strokeWidth={1.5} />
        </div>
      </div>
    </aside>
  )
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <main className="min-w-0 flex-1 px-6 pt-5 pb-24">{children}</main>
      <OperatorDrawer />
    </div>
  )
}
