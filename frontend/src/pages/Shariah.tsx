import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { fmtDate, fmtNum } from "../lib/format";
import { MARKETS, useMarket } from "../lib/market";
import type { Methodology, ScreenerResponse, ShariahStatus } from "../lib/types";
import { ShariahBadge } from "../components/badges";
import { ResultChip } from "../components/ShariahPanel";
import { Card, EmptyState } from "../components/ui";

const STATUSES: ShariahStatus[] = ["COMPLIANT", "QUESTIONABLE", "NON_COMPLIANT", "INSUFFICIENT_DATA", "UNDER_REVIEW", "NOT_SCREENED"];
const RATIO_COLS: [string, string][] = [["debt", "Debt"], ["cash_securities", "Cash + securities"], ["receivables", "Receivables"], ["income", "Non-perm. income"]];

export default function Shariah() {
  const { market } = useMarket();
  const label = MARKETS.find((m) => m.code === market)?.label ?? market;
  const [mid, setMid] = useState<number | null>(null);
  const [status, setStatus] = useState<ShariahStatus | "">("");
  const meths = useQuery({ queryKey: ["methodologies"], queryFn: () => api<Methodology[]>("/api/shariah/methodologies") });
  const q = useQuery({
    queryKey: ["shariah-screener", market, mid, status],
    queryFn: () => api<ScreenerResponse>(
      `/api/shariah/screener?market=${market}${mid ? `&methodology_id=${mid}` : ""}${status ? `&status=${status}` : ""}&include_unscreened=${status === "NOT_SCREENED"}`),
  });
  const d = q.data;
  const cols = RATIO_COLS.filter(([k]) => d?.results.some((r) => k in r.ratios));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Shariah Screening · {label}</h1>
          <p className="text-xs text-ink-400">Business-activity and ratio screens on the figures stored in the platform. No data provider is called.</p>
        </div>
        <label className="text-[11px] text-ink-400">Methodology
          <select className="ml-2 rounded-md border border-ink-700 bg-ink-950 px-2 py-1 text-xs text-ink-100"
            value={mid ?? d?.methodology.id ?? ""} onChange={(e) => setMid(Number(e.target.value))}>
            {meths.data?.map((m) => <option key={m.id} value={m.id}>{m.name}{m.is_default && !/default/i.test(m.name) ? " (default)" : ""}</option>)}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Status">
        <button role="tab" aria-selected={status === ""} onClick={() => setStatus("")}
          className={`rounded-md px-2.5 py-1 text-xs ${status === "" ? "bg-ink-800 text-ink-100 ring-1 ring-ink-700" : "text-ink-400 hover:text-ink-100"}`}>
          Screened <span className="num text-ink-500">{d ? d.total - d.counts.NOT_SCREENED : ""}</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s} role="tab" aria-selected={status === s} onClick={() => setStatus(s)}
            className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs ${status === s ? "bg-ink-800 ring-1 ring-ink-700" : "hover:bg-ink-850"}`}>
            <ShariahBadge status={s} /><span className="num text-ink-400">{d?.counts[s] ?? ""}</span>
          </button>
        ))}
      </div>

      <Card>
        {q.isLoading ? <p className="text-sm text-ink-400">Screening…</p> : q.isError ? (
          <p role="alert" className="text-sm text-red-400">{(q.error as Error).message}</p>
        ) : !d || d.results.length === 0 ? (
          <EmptyState title={status ? "No stock has this status" : "No stock has been screened yet"}>
            Open a stock, then add its business activities and the figures from its latest financial statements under
            "Screening inputs". The free EODHD plan carries no fundamentals, so these are entered by hand with a source reference.
          </EmptyState>
        ) : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm [&_td]:whitespace-nowrap">
              <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                <tr>{["Stock", "Status", "Primary business", ...cols.map(([, l]) => l), "Fundamentals to", "First reason"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {d.results.map((r) => (
                  <tr key={`${r.exchange}-${r.ticker}`} className="hover:bg-ink-850">
                    <td className="px-4 py-2.5">
                      <Link to={`/stocks/${r.exchange}/${encodeURIComponent(r.ticker)}#shariah-h`} className="font-medium hover:text-brand-500">{r.ticker}</Link>
                      <p className="max-w-[180px] truncate text-[11px] text-ink-400">{r.name}</p>
                    </td>
                    <td className="px-4 py-2.5"><ShariahBadge status={r.status} /></td>
                    <td className="max-w-[180px] truncate px-4 py-2.5 text-xs text-ink-300">{r.primary ?? "n/a"}</td>
                    {cols.map(([k]) => {
                      const x = r.ratios[k];
                      return (
                        <td key={k} className="px-4 py-2.5 text-xs">
                          {x ? <span className="inline-flex items-center gap-1.5"><span className="num">{x.value === null ? "n/a" : `${fmtNum(x.value * 100, 1)}%`}</span><ResultChip r={x.result} /></span> : "n/a"}
                        </td>
                      );
                    })}
                    <td className={`px-4 py-2.5 text-xs ${r.fresh === false ? "text-amber-300" : "text-ink-300"}`}>{fmtDate(r.period_end)}</td>
                    <td className="max-w-[280px] truncate px-4 py-2.5 text-[11px] text-ink-400" title={r.first_reason ?? ""}>{r.first_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {d && <p className="text-[11px] text-ink-500">{d.note} Methodology: {d.methodology.name}. Edit or copy methodologies in Settings.</p>}
    </div>
  );
}
