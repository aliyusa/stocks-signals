import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Bell, BookOpenCheck, Briefcase, Calculator, FlaskConical, Globe2, LayoutDashboard, ListChecks, LogOut, Menu,
  Radar, Settings, ShieldCheck, Sparkles, Star, X,
} from "lucide-react";
import { useAuth } from "../lib/auth";
import { MARKETS, useMarket } from "../lib/market";
import AlertBell from "./AlertBell";
import SearchBox from "./SearchBox";
import { Disclaimer } from "./ui";

export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, phase: 1 },
  { to: "/markets", label: "Markets", icon: Globe2, phase: 2 },
  { to: "/scanner", label: "Stock Scanner", icon: Radar, phase: 3 },
  { to: "/signals", label: "Signals", icon: Sparkles, phase: 3 },
  { to: "/watchlist", label: "Watchlist", icon: Star, phase: 5 },
  { to: "/portfolio", label: "Portfolio", icon: Briefcase, phase: 5 },
  { to: "/backtesting", label: "Backtesting", icon: FlaskConical, phase: 6 },
  { to: "/strategies", label: "Strategies", icon: ListChecks, phase: 6 },
  { to: "/alerts", label: "Alerts", icon: Bell, phase: 5 },
  { to: "/shariah", label: "Shariah Screening", icon: ShieldCheck, phase: 4 },
  { to: "/risk", label: "Risk Calculator", icon: Calculator, phase: 6 },
  { to: "/settings", label: "Settings", icon: Settings, phase: 1 },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col gap-1 p-3" aria-label="Main">
      <div className="mb-4 flex items-center gap-2 px-2 pt-1">
        <img src="/favicon.svg" alt="" className="h-7 w-7" />
        <div className="leading-tight">
          <p className="text-sm font-bold text-ink-100">Halal Stock Signals</p>
          <p className="text-[10px] uppercase tracking-widest text-ink-500">Research platform</p>
        </div>
      </div>
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              isActive ? "bg-brand-600/15 font-medium text-brand-500" : "text-ink-300 hover:bg-ink-800 hover:text-ink-100"
            }`
          }
        >
          <Icon size={16} aria-hidden />
          {label}
        </NavLink>
      ))}
      <div className="mt-auto rounded-lg border border-ink-800 p-3 text-[11px] text-ink-400">
        <BookOpenCheck size={14} className="mb-1 text-brand-500" aria-hidden />
        No trade is ever placed by this platform. Every signal shows its data and reasoning.
      </div>
    </nav>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { market, setMarket } = useMarket();
  const [open, setOpen] = useState(false);

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 border-r border-ink-800 bg-ink-900 lg:block">
        <Sidebar />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 overflow-y-auto border-r border-ink-800 bg-ink-900">
            <button className="absolute right-3 top-3 p-1 text-ink-400" onClick={() => setOpen(false)} aria-label="Close menu">
              <X size={18} />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-ink-800 bg-ink-950/90 px-4 py-2.5 backdrop-blur">
          <button className="p-1 text-ink-300 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <SearchBox />
          <div className="hidden min-w-0 flex-1 gap-1 overflow-x-auto md:flex" role="tablist" aria-label="Market">
            {MARKETS.map((m) => (
              <button
                key={m.code}
                role="tab"
                aria-selected={market === m.code}
                onClick={() => setMarket(m.code)}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  market === m.code ? "bg-ink-800 text-ink-100 ring-1 ring-ink-700" : "text-ink-400 hover:text-ink-100"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <AlertBell />
          <span className="hidden text-xs text-ink-400 sm:inline">{user?.full_name || user?.email}</span>
          <button onClick={logout} className="rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100" aria-label="Log out" title="Log out">
            <LogOut size={16} />
          </button>
        </header>

        <div className="flex gap-1 overflow-x-auto border-b border-ink-800 px-4 py-2 md:hidden" role="tablist" aria-label="Market">
          {MARKETS.map((m) => (
            <button key={m.code} role="tab" aria-selected={market === m.code} onClick={() => setMarket(m.code)}
              className={`whitespace-nowrap rounded-md px-3 py-1 text-xs font-medium ${market === m.code ? "bg-ink-800 text-ink-100" : "text-ink-400"}`}>
              {m.label}
            </button>
          ))}
        </div>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
            <Outlet />
            <footer className="mt-10 border-t border-ink-800 pt-4">
              <Disclaimer />
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}
