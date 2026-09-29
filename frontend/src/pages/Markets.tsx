import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CloudDownload } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtMoney, fmtPct } from "../lib/format";
import { MARKETS, useMarket } from "../lib/market";
import type { StockRow, Usage } from "../lib/types";
import { DataStatusBadge } from "../components/badges";
import { Card, EmptyState } from "../components/ui";

export default function Markets() {
  const { market } = useMarket();
  const qc = useQueryClient();
  const label = MARKETS.find((m) => m.code === market)?.label ?? market;
  const stocks = useQuery({
    queryKey: ["stocks", market],
    queryFn: () => api<{ results: StockRow[] }>(`/api/stocks?market=${market}&limit=500`),
  });
  const usage = useQuery({ queryKey: ["usage"], queryFn: () => api<{ eodhd: Usage }>("/api/usage") });
  const importNgx = useMutation({
    mutationFn: () => api<{ imported: number; error: string | null; usage: Usage }>("/api/exchanges/XNSA/import", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stocks"] });
      qc.invalidateQueries({ queryKey: ["usage"] });
    },
  });
  const rows = (stocks.data?.results ?? []).filter((s) => s.type !== "index");
  const u = usage.data?.eodhd;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Markets · {label}</h1>
          <p className="text-xs text-ink-400">Stocks in your local universe. Prices are the last stored end-of-day close.</p>
        </div>
        {u && (
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wider text-ink-500">EODHD calls today</p>
            <div className="mt-1 h-1.5 w-40 overflow-hidden rounded-full bg-ink-800">
              <div className="h-full bg-brand-500" style={{ width: `${Math.min(100, (u.used / Math.max(1, u.limit)) * 100)}%` }} />
            </div>
            <p className="num mt-1 text-xs text-ink-300">{u.used} of {u.limit} used</p>
          </div>
        )}
      </div>

      {(market === "NG" || market === "GLOBAL") && (
        <Card title="Nigerian Exchange (NGX) universe">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-2xl text-xs leading-relaxed text-ink-400">
              Import the full NGX symbol list from EODHD in one API call. This adds names and tickers only; prices are
              fetched per stock when you open it, so the free 20-calls-a-day budget goes on the stocks you study.
            </p>
            <button
              onClick={() => importNgx.mutate()}
              disabled={importNgx.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-60"
            >
              <CloudDownload size={14} /> {importNgx.isPending ? "Importing…" : "Import NGX list (1 call)"}
            </button>
          </div>
          {importNgx.data && (
            <p className={`mt-2 text-xs ${importNgx.data.error ? "text-amber-300" : "text-emerald-300"}`}>
              {importNgx.data.error ?? `Imported or updated ${importNgx.data.imported} equities.`}
            </p>
          )}
          {importNgx.isError && <p className="mt-2 text-xs text-red-400">{(importNgx.error as Error).message}</p>}
        </Card>
      )}

      <Card title={`${rows.length} instruments`}>
        {!rows.length ? (
          <EmptyState title="No stocks in this market yet">
            Use the search box at the top and press "Search EODHD" to add a stock, or import the NGX list above.
          </EmptyState>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                <tr>{["Ticker", "Name", "Exchange", "Last close", "Change", "Status", "Close date"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {rows.map((s) => (
                  <tr key={`${s.exchange}:${s.ticker}`} className="hover:bg-ink-850">
                    <td className="px-4 py-2.5 font-semibold"><Link to={`/stocks/${s.exchange}/${encodeURIComponent(s.ticker)}`} className="hover:text-brand-500">{s.ticker}</Link></td>
                    <td className="max-w-[16rem] truncate px-4 py-2.5 text-ink-300">{s.name}</td>
                    <td className="px-4 py-2.5 text-xs text-ink-400">{s.exchange}</td>
                    <td className="num px-4 py-2.5">{s.quote.price === null ? <span className="text-ink-500">Data unavailable</span> : fmtMoney(s.quote.price, s.currency)}</td>
                    <td className={`num px-4 py-2.5 ${s.quote.change_pct === null ? "text-ink-500" : s.quote.change_pct >= 0 ? "text-up" : "text-down"}`}>{fmtPct(s.quote.change_pct)}</td>
                    <td className="px-4 py-2.5"><DataStatusBadge status={s.quote.status} title={s.quote.note ?? undefined} /></td>
                    <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDate(s.quote.as_of)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
