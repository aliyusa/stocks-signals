import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { fmtCompact, fmtDate, fmtDateTime, fmtMoney, fmtPct } from "../lib/format";
import type { AnalysisResponse, BarsResponse, StockDetail as SD } from "../lib/types";
import { DataStatusBadge, SignalBadge } from "../components/badges";
import PriceChart, { OVERLAYS, Swatch, type OverlayKey, type PriceLevel } from "../components/PriceChart";
import { AnalysisGrid } from "../components/AnalysisPanel";
import { Card, EmptyState } from "../components/ui";

const RANGES = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y", "MAX"] as const;
const INTRADAY = new Set(["1D", "5D"]);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-ink-500">{label}</dt>
      <dd className="num mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

export default function StockDetail() {
  const { mic = "", ticker = "" } = useParams();
  const qc = useQueryClient();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const [overlays, setOverlays] = useState<OverlayKey[]>(["sma50", "sma200"]);
  const [showLevels, setShowLevels] = useState(true);
  const [panes, setPanes] = useState<("rsi" | "macd")[]>(["rsi", "macd"]);
  const base = `/api/stocks/${mic}/${encodeURIComponent(ticker)}`;

  const detail = useQuery({ queryKey: ["stock", mic, ticker], queryFn: () => api<SD>(base) });
  const bars = useQuery({
    queryKey: ["bars", mic, ticker, range],
    queryFn: () => api<BarsResponse>(`${base}/bars?range=${range}`),
    enabled: detail.isSuccess && !INTRADAY.has(range),
  });
  const analysis = useQuery({
    queryKey: ["analysis", mic, ticker, range],
    queryFn: () => api<AnalysisResponse>(`${base}/analysis?range=${range}`),
    enabled: detail.isSuccess && !INTRADAY.has(range),
  });
  const refresh = useMutation({
    mutationFn: () => api<{ status: string; message: string | null }>(`${base}/refresh`, { method: "POST" }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["stock", mic, ticker] });
      qc.invalidateQueries({ queryKey: ["bars", mic, ticker] });
      qc.invalidateQueries({ queryKey: ["analysis", mic, ticker] });
    },
  });

  if (detail.isLoading) return <p className="text-sm text-ink-400">Loading {ticker}…</p>;
  if (detail.isError || !detail.data)
    return (
      <div className="space-y-3">
        <Link to="/markets" className="inline-flex items-center gap-1 text-xs text-ink-400 hover:text-ink-100"><ArrowLeft size={14} /> Markets</Link>
        <p role="alert" className="text-sm text-red-400">{(detail.error as Error)?.message}</p>
      </div>
    );

  const d = detail.data;
  const q = d.quote;
  const up = (q.change_pct ?? 0) >= 0;
  const refreshMsg = refresh.data?.message ?? d.refresh?.message;
  const a = analysis.data?.available ? analysis.data : null;
  const sig = a?.signal;
  const levels: PriceLevel[] = [];
  if (sig && showLevels) {
    if (sig.entry_low !== null) levels.push({ price: sig.entry_low, title: "Entry low", kind: "entry" });
    if (sig.entry_high !== null) levels.push({ price: sig.entry_high, title: "Entry high", kind: "entry" });
    if (sig.stop !== null) levels.push({ price: sig.stop, title: "Stop", kind: "stop" });
    sig.targets.forEach((t) => t.price !== null && levels.push({ price: t.price, title: t.name.replace("Target ", "T"), kind: "target" }));
  }
  const toggle = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  return (
    <div className="space-y-6">
      <Link to="/markets" className="inline-flex items-center gap-1 text-xs text-ink-400 hover:text-ink-100"><ArrowLeft size={14} /> Markets</Link>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold">{d.ticker}</h1>
            <span className="rounded bg-ink-800 px-1.5 py-0.5 text-[11px] text-ink-300">{d.exchange_name}</span>
            <span className="rounded bg-ink-800 px-1.5 py-0.5 text-[11px] uppercase text-ink-300">{d.type}</span>
          </div>
          <p className="mt-1 text-sm text-ink-300">{d.name}</p>
        </div>
        <div className="sm:text-right">
          <p className="num text-2xl font-semibold">{fmtMoney(q.price, d.currency)}</p>
          <p className={`num text-sm ${q.change_pct === null ? "text-ink-400" : up ? "text-up" : "text-down"}`}>
            {q.change_pct === null ? "Change n/a" : `${fmtPct(q.change_pct)} vs previous close`}
          </p>
          <div className="mt-1 flex items-center gap-2 sm:justify-end">
            <DataStatusBadge status={q.status} title={q.note ?? undefined} />
            <span className="text-[11px] text-ink-500">{q.as_of ? `Close of ${fmtDate(q.as_of)}` : ""}</span>
          </div>
        </div>
      </header>

      {refreshMsg && (
        <div className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {refreshMsg}
        </div>
      )}

      <Card
        title="Price chart · daily"
        action={
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Range">
            {RANGES.map((r) => (
              <button
                key={r}
                role="tab"
                aria-selected={range === r}
                disabled={INTRADAY.has(r)}
                title={INTRADAY.has(r) ? "Needs intraday data; your EODHD plan provides end-of-day bars" : undefined}
                onClick={() => setRange(r)}
                className={`rounded px-2 py-1 text-[11px] font-medium ${range === r ? "bg-brand-600/20 text-brand-500" : "text-ink-400 hover:text-ink-100"} disabled:cursor-not-allowed disabled:opacity-40`}
              >
                {r}
              </button>
            ))}
          </div>
        }
      >
        {bars.data && bars.data.bars.length ? (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px]" aria-label="Chart overlays">
              {(Object.keys(OVERLAYS) as OverlayKey[]).map((k) => (
                <label key={k} className="inline-flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" className="accent-teal-500" checked={overlays.includes(k)} onChange={() => setOverlays(toggle(overlays, k))} disabled={!a} />
                  <Swatch color={OVERLAYS[k].color} label={OVERLAYS[k].label} dashed={k === "bb"} />
                </label>
              ))}
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-ink-300">
                <input type="checkbox" className="accent-teal-500" checked={showLevels} onChange={() => setShowLevels(!showLevels)} disabled={!sig} />
                Entry, stop and targets
              </label>
              {(["rsi", "macd"] as const).map((p) => (
                <label key={p} className="inline-flex cursor-pointer items-center gap-1.5 text-ink-300">
                  <input type="checkbox" className="accent-teal-500" checked={panes.includes(p)} onChange={() => setPanes(toggle(panes, p))} disabled={!a} />
                  {p.toUpperCase()} pane
                </label>
              ))}
            </div>
            <PriceChart data={bars.data} series={a?.series} overlays={a ? overlays : []} levels={levels} panes={a ? panes : []} />
            <p className="mt-2 text-[11px] text-ink-500">
              {bars.data.bars.length} daily bars · {bars.data.note} Source: {q.source ?? "n/a"}.
            </p>
          </>
        ) : bars.isLoading ? (
          <p className="text-sm text-ink-400">Loading bars…</p>
        ) : (
          <EmptyState title="Data unavailable">No price history is stored for this instrument yet. {d.refresh?.message}</EmptyState>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Snapshot">
          <dl className="grid grid-cols-2 gap-4">
            <Field label="Last close">{fmtMoney(q.price, d.currency)}</Field>
            <Field label="Previous close">{fmtMoney(q.previous_close ?? null, d.currency)}</Field>
            <Field label="Volume">{fmtCompact(q.volume ?? null)}</Field>
            <Field label="Currency">{d.currency ?? "n/a"}</Field>
            <Field label="Country">{d.country ?? "n/a"}</Field>
            <Field label="ISIN">{d.isin ?? "n/a"}</Field>
          </dl>
        </Card>

        <Card title="Shariah status & signal">
          <ul className="space-y-3 text-sm">
            <li className="flex items-center justify-between gap-2">
              <span className="text-ink-300">Shariah screen</span>
              <span className="rounded-md bg-ink-800 px-2 py-0.5 text-[11px] font-semibold text-ink-300 ring-1 ring-ink-700">NOT YET SCREENED</span>
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="text-ink-300">Technical signal</span>
              {sig ? <SignalBadge type={sig.signal_type} /> : (
                <span className="rounded-md bg-ink-800 px-2 py-0.5 text-[11px] font-semibold text-ink-300 ring-1 ring-ink-700">NOT COMPUTED</span>
              )}
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="text-ink-300">Setup score</span>
              <span className="num">{sig?.score != null ? `${sig.score.toFixed(0)}/100` : "n/a"}</span>
            </li>
          </ul>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
            {analysis.data && !analysis.data.available ? analysis.data.reason + " " : ""}
            The Shariah engine arrives in Phase 4. Until then no compliance status is implied.
          </p>
        </Card>

        <Card
          title="Data quality"
          action={
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="inline-flex items-center gap-1 rounded-md bg-ink-800 px-2 py-1 text-[11px] text-ink-100 ring-1 ring-ink-700 hover:bg-ink-700 disabled:opacity-60"
              title="Forces a provider request (1 EODHD call)"
            >
              <RefreshCw size={12} className={refresh.isPending ? "animate-spin" : ""} /> Refresh
            </button>
          }
        >
          <dl className="grid grid-cols-2 gap-4">
            <Field label="Daily bars stored">{d.data_quality.bars}</Field>
            <Field label="Frequency">{q.frequency ?? "n/a"}</Field>
            <Field label="First bar">{fmtDate(d.data_quality.first)}</Field>
            <Field label="Last bar">{fmtDate(d.data_quality.last)}</Field>
            <Field label="Flat bars (last 60)">
              {d.data_quality.zero_range_share_60 === null ? "n/a" : `${Math.round(d.data_quality.zero_range_share_60 * 100)}%`}
            </Field>
            <Field label="EODHD calls today">{d.usage.used}/{d.usage.limit}</Field>
          </dl>
          {d.data_quality.warnings.length > 0 && (
            <ul className="mt-3 space-y-1">
              {d.data_quality.warnings.map((w) => (
                <li key={w} className="flex gap-1.5 text-[11px] leading-snug text-amber-300"><AlertTriangle size={12} className="mt-0.5 shrink-0" />{w}</li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] text-ink-500">Checked {fmtDateTime(new Date().toISOString())}. Status: {q.note ?? "up to date for the latest expected session"}.</p>
        </Card>
      </div>

      {analysis.isLoading && <p className="text-sm text-ink-400">Computing indicators…</p>}
      {analysis.isError && <p role="alert" className="text-sm text-red-400">Analysis failed: {(analysis.error as Error).message}</p>}
      {a && sig && <AnalysisGrid s={sig} currency={d.currency} strategy={a.strategy} />}
    </div>
  );
}
