import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { fmtDate, fmtDateTime, fmtMoney } from "../lib/format";
import { MARKETS, useMarket } from "../lib/market";
import type { SignalListRow, SignalType } from "../lib/types";
import { SignalBadge } from "../components/badges";
import { Card, EmptyState } from "../components/ui";

const TYPES: SignalType[] = ["BUY_SETUP", "WATCHLIST", "WAIT", "AVOID"];

export default function Signals() {
  const { market } = useMarket();
  const [type, setType] = useState<SignalType | "">("");
  const label = MARKETS.find((m) => m.code === market)?.label ?? market;
  const q = useQuery({
    queryKey: ["signals", market, type],
    queryFn: () => api<{ strategy: string; results: SignalListRow[] }>(`/api/signals?market=${market}${type ? `&type=${type}` : ""}`),
  });
  const rows = q.data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Signals · {label}</h1>
          <p className="text-xs text-ink-400">
            Latest signal per stock under "{q.data?.strategy ?? "…"}". A signal is stored each time a stock is opened, refreshed or scanned.
          </p>
        </div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Signal type">
          {(["", ...TYPES] as const).map((t) => (
            <button key={t || "all"} role="tab" aria-selected={type === t} onClick={() => setType(t)}
              className={`rounded px-2 py-1 text-[11px] font-medium ${type === t ? "bg-brand-600/20 text-brand-500" : "text-ink-400 hover:text-ink-100"}`}>
              {t ? t.replace("_", " ") : "All"}
            </button>
          ))}
        </div>
      </div>

      <Card>
        {q.isLoading ? <p className="text-sm text-ink-400">Loading…</p> : q.isError ? (
          <p role="alert" className="text-sm text-red-400">{(q.error as Error).message}</p>
        ) : rows.length === 0 ? (
          <EmptyState title="No signals yet">Open a stock page or run the Stock Scanner to compute signals from stored price history.</EmptyState>
        ) : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm [&_td]:whitespace-nowrap">
              <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                <tr>{["Stock", "Signal", "Score", "Coverage", "Entry zone", "Stop", "Target 1", "R:R", "Data as of", "Computed", "Top warning"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {rows.map((r) => (
                  <tr key={`${r.exchange}-${r.ticker}`} className="hover:bg-ink-850">
                    <td className="px-4 py-2.5">
                      <Link to={`/stocks/${r.exchange}/${encodeURIComponent(r.ticker)}`} className="font-medium hover:text-brand-500">{r.ticker}</Link>
                      <p className="max-w-[180px] truncate text-[11px] text-ink-400">{r.name}</p>
                    </td>
                    <td className="px-4 py-2.5"><SignalBadge type={r.signal} /></td>
                    <td className="num px-4 py-2.5">{r.score === null ? "n/a" : r.score.toFixed(0)}</td>
                    <td className="num px-4 py-2.5 text-ink-300">{r.coverage === null ? "n/a" : `${Math.round(r.coverage * 100)}%`}</td>
                    <td className="num px-4 py-2.5 text-xs">{r.entry_low === null ? "n/a" : `${fmtMoney(r.entry_low, r.currency)} to ${fmtMoney(r.entry_high, null)}`}</td>
                    <td className="num px-4 py-2.5 text-xs">{r.stop === null ? "n/a" : fmtMoney(r.stop, r.currency)}</td>
                    <td className="num px-4 py-2.5 text-xs">{r.target1 === null ? "n/a" : fmtMoney(r.target1, r.currency)}</td>
                    <td className="num px-4 py-2.5 text-xs">{r.risk_reward === null ? "n/a" : `${r.risk_reward.toFixed(2)} : 1`}</td>
                    <td className="px-4 py-2.5 text-xs text-ink-300">{fmtDate(r.data_as_of)}</td>
                    <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDateTime(r.created_at)}</td>
                    <td className="max-w-[240px] px-4 py-2.5 text-[11px] text-amber-300">{r.warnings[0] ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="text-[11px] text-ink-500">Signals describe setups; they are not instructions to trade.</p>
    </div>
  );
}
