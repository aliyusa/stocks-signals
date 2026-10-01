import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownRight, ArrowUpRight } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtDateTime, fmtNum, fmtPct } from "../lib/format";
import { useMarket } from "../lib/market";
import type { Dashboard as D, SignalRow } from "../lib/types";
import { DataStatusBadge, SignalBadge } from "../components/badges";
import { Card, EmptyState, Stat } from "../components/ui";

function IndexCard({ c }: { c: D["index_cards"][number] }) {
  const v = c.change_pct.value;
  const up = v !== null && v >= 0;
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-ink-400">{c.label}</p>
        <DataStatusBadge status={c.change_pct.status} title={c.change_pct.note ?? undefined} />
      </div>
      {c.change_pct.level !== undefined && c.change_pct.level !== null && (
        <p className="num mt-2 text-lg font-semibold text-ink-100">{c.change_pct.level.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</p>
      )}
      {v === null ? (
        <p className="mt-2 text-sm font-medium text-ink-400">{c.change_pct.level ? "Change n/a" : "Data unavailable"}</p>
      ) : (
        <p className={`num mt-2 flex items-center gap-1 text-2xl font-semibold ${up ? "text-up" : "text-down"}`}>
          {up ? <ArrowUpRight size={20} /> : <ArrowDownRight size={20} />}
          {fmtPct(v)}
        </p>
      )}
      <p className="mt-2 line-clamp-2 text-[11px] leading-snug text-ink-500">
        {c.change_pct.status === "UNAVAILABLE"
          ? c.change_pct.note
          : `${c.change_pct.source} · close of ${fmtDate(c.change_pct.as_of)}${c.change_pct.note ? ` · ${c.change_pct.note}` : ""}`}
      </p>
    </div>
  );
}

function SetupsTable({ rows, empty }: { rows: SignalRow[]; empty?: string }) {
  if (!rows.length && empty) return <EmptyState title={empty}>Signals are recorded here with the data date they were computed from.</EmptyState>;
  if (!rows.length)
    return (
      <EmptyState title="No potential Shariah-compliant setups yet">
        A setup appears here only when its stock is COMPLIANT under your default methodology. Add business activities and
        fundamentals on a stock page to screen it. Nothing is shown until real data supports it.
      </EmptyState>
    );
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
          <tr>
            {["Ticker", "Setup", "Score", "R:R", "Data as of"].map((h) => (
              <th key={h} className="px-4 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-800">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-ink-850">
              <td className="px-4 py-2.5"><span className="font-semibold">{r.ticker}</span> <span className="text-ink-400">{r.name}</span></td>
              <td className="px-4 py-2.5"><SignalBadge type={r.signal} /></td>
              <td className="num px-4 py-2.5">{r.score === null ? "n/a" : `${fmtNum(r.score, 0)}/100`}</td>
              <td className="num px-4 py-2.5">{r.risk_reward === null ? "n/a" : `${fmtNum(r.risk_reward, 2)} : 1`}</td>
              <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDateTime(r.data_as_of)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Dashboard() {
  const { market } = useMarket();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<D>("/api/dashboard"), refetchInterval: 60_000 });

  if (q.isLoading) return <p className="text-sm text-ink-400">Loading dashboard…</p>;
  if (q.isError || !q.data)
    return <p role="alert" className="text-sm text-red-400">Could not load the dashboard: {(q.error as Error)?.message}</p>;

  const d = q.data;
  const cards = d.index_cards.filter((c) => market === "GLOBAL" || c.market === market);
  const noProviders = d.data_sources.filter((s) => s.kind === "price" && s.code !== "csv").every((s) => !s.enabled);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-xs text-ink-400">Generated {fmtDateTime(d.generated_at)}</p>
        </div>
      </div>

      {noProviders && (
        <div className="flex gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-400" />
          <div>
            <p className="font-medium text-amber-200">No market-data provider is connected yet</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-300">
              Every price below is shown as UNAVAILABLE rather than estimated. Set <code>EODHD_API_KEY</code> in <code>.env</code> and restart
              the backend. See <Link to="/settings" className="text-brand-500 hover:underline">Settings → Data sources</Link>.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.length ? cards.map((c) => <IndexCard key={c.symbol} c={c} />) : (
          <div className="sm:col-span-2 lg:col-span-3"><EmptyState title="No index card configured for this market yet" /></div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Shariah-compliant stocks" value={d.counts.shariah_compliant} hint={`of ${d.counts.stock_universe} in universe`} />
        <Stat label="Potential setups" value={d.counts.potential_setups} hint="last 7 days, compliant only" />
        <Stat label="Watchlist stocks" value={d.counts.watchlist_stocks} />
        <Stat label="Unread alerts" value={d.counts.unread_alerts} />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card title="Potential Shariah-compliant setups" className="xl:col-span-2">
          <SetupsTable rows={d.top_setups} />
        </Card>
        <Card title="Market regime">
          <ul className="space-y-3">
            {Object.entries(d.market_regime).map(([m, dp]) => (
              <li key={m} className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{m === "NG" ? "NGX" : m === "US" ? "US markets" : m}</p>
                  <p className="text-xs text-ink-400">{dp.value ?? dp.note}</p>
                </div>
                <DataStatusBadge status={dp.status} />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card title="Recent signals" className="xl:col-span-2">
          <SetupsTable rows={d.recent_signals} empty="No signals generated yet" />
        </Card>
        <Card title="Data sources">
          <ul className="divide-y divide-ink-800">
            {d.data_sources.map((s) => (
              <li key={s.code} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm">{s.name}</p>
                  <p className="text-[11px] text-ink-500">{s.kind} · {s.tier} · {s.frequency}</p>
                </div>
                <DataStatusBadge status={s.status} title={s.last_error ?? (s.enabled ? "Configured, awaiting first fetch" : "Not configured")} />
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
