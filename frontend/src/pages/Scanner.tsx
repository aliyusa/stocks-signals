import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtMoney, fmtNum } from "../lib/format";
import { MARKETS, useMarket } from "../lib/market";
import type { ScanResponse, ShariahStatus, SignalType } from "../lib/types";
import { ShariahBadge, SignalBadge } from "../components/badges";
import { Card, EmptyState } from "../components/ui";

type Flags = "above_sma50" | "above_sma200" | "sma50_gt_sma200" | "macd_positive" | "volume_above_avg" | "volume_spike" | "breakout" | "near_52w_high" | "exclude_illiquid";
const FLAGS: [Flags, string][] = [
  ["above_sma50", "Price above SMA 50"], ["above_sma200", "Price above SMA 200"], ["sma50_gt_sma200", "SMA 50 above SMA 200"],
  ["macd_positive", "MACD above signal"], ["volume_above_avg", "Volume above 20-day average"], ["volume_spike", "Volume spike (2× average)"],
  ["breakout", "Close above prior 20-day high"], ["near_52w_high", "Within 5% of 52-week high"], ["exclude_illiquid", "Exclude illiquid stocks"],
];
const TYPES: SignalType[] = ["BUY_SETUP", "WATCHLIST", "WAIT", "AVOID"];
const SHARIAH: ShariahStatus[] = ["COMPLIANT", "QUESTIONABLE", "NON_COMPLIANT", "INSUFFICIENT_DATA", "UNDER_REVIEW", "NOT_SCREENED"];
type Nums = "min_score" | "rsi_min" | "rsi_max" | "price_min" | "price_max" | "max_atr_pct";
const NUMS: [Nums, string, number, number][] = [
  ["min_score", "Min setup score", 0, 100], ["rsi_min", "RSI min", 0, 100], ["rsi_max", "RSI max", 0, 100],
  ["price_min", "Price min", 0, 1e9], ["price_max", "Price max", 0, 1e9], ["max_atr_pct", "Max ATR % of price", 0, 100],
];

export default function Scanner() {
  const { market } = useMarket();
  const label = MARKETS.find((m) => m.code === market)?.label ?? market;
  const [flags, setFlags] = useState<Record<Flags, boolean>>(
    Object.fromEntries(FLAGS.map(([k]) => [k, k === "exclude_illiquid"])) as Record<Flags, boolean>);
  const [nums, setNums] = useState<Record<Nums, string>>(Object.fromEntries(NUMS.map(([k]) => [k, ""])) as Record<Nums, string>);
  const [types, setTypes] = useState<SignalType[]>([]);
  const [shariah, setShariah] = useState<ShariahStatus[]>([]);

  const scan = useMutation({
    mutationFn: () => api<ScanResponse>("/api/scanner", {
      method: "POST",
      body: JSON.stringify({
        market, signal_types: types, shariah, ...flags,
        ...Object.fromEntries(NUMS.map(([k]) => [k, nums[k] === "" ? null : Number(nums[k])])),
      }),
    }),
  });
  const res = scan.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Stock Scanner · {label}</h1>
        <p className="text-xs text-ink-400">Runs on stored end-of-day bars only. It never calls EODHD, so it uses none of your daily calls.</p>
      </div>

      <Card title="Filters" action={
        <button onClick={() => scan.mutate()} disabled={scan.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-60">
          <Radar size={14} className={scan.isPending ? "animate-spin" : ""} /> {scan.isPending ? "Scanning…" : "Run scan"}
        </button>
      }>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); scan.mutate(); }}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {NUMS.map(([k, lbl, min, max]) => (
              <label key={k} className="text-[11px] text-ink-400">
                {lbl}
                <input type="number" inputMode="decimal" min={min} max={max} step="any" value={nums[k]}
                  onChange={(e) => setNums({ ...nums, [k]: e.target.value })}
                  className="num mt-1 w-full rounded-md border border-ink-700 bg-ink-950 px-2 py-1.5 text-sm text-ink-100" />
              </label>
            ))}
          </div>
          <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Conditions</legend>
            {FLAGS.map(([k, lbl]) => (
              <label key={k} className="inline-flex items-center gap-2 text-xs text-ink-300">
                <input type="checkbox" className="accent-teal-500" checked={flags[k]} onChange={() => setFlags({ ...flags, [k]: !flags[k] })} /> {lbl}
              </label>
            ))}
          </fieldset>
          <fieldset className="flex flex-wrap gap-3">
            <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Signal type (none ticked = any)</legend>
            {TYPES.map((t) => (
              <label key={t} className="inline-flex items-center gap-2 text-xs text-ink-300">
                <input type="checkbox" className="accent-teal-500" checked={types.includes(t)}
                  onChange={() => setTypes(types.includes(t) ? types.filter((x) => x !== t) : [...types, t])} /> {t.replace("_", " ")}
              </label>
            ))}
          </fieldset>
          <fieldset className="flex flex-wrap gap-3">
            <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Shariah status under your default methodology (none ticked = any)</legend>
            {SHARIAH.map((t) => (
              <label key={t} className="inline-flex items-center gap-2 text-xs text-ink-300">
                <input type="checkbox" className="accent-teal-500" checked={shariah.includes(t)}
                  onChange={() => setShariah(shariah.includes(t) ? shariah.filter((x) => x !== t) : [...shariah, t])} /> <ShariahBadge status={t} />
              </label>
            ))}
          </fieldset>
          <button type="submit" className="sr-only">Run scan</button>
        </form>
      </Card>

      {scan.isError && <p role="alert" className="text-sm text-red-400">{(scan.error as Error).message}</p>}
      {res && (
        <Card title={`${res.results.length} match${res.results.length === 1 ? "" : "es"} · ${res.scanned} scanned${res.skipped_short_history ? ` · ${res.skipped_short_history} skipped (under 30 bars)` : ""}`}>
          {res.results.length === 0 ? (
            <EmptyState title="No stock matches these filters">{res.note}</EmptyState>
          ) : (
            <div className="-mx-4 -my-4 overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm [&_td]:whitespace-nowrap">
                <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                  <tr>{["Stock", "Close", "As of", "Signal", "Score", "RSI", "Daily trend", "Vol ÷ avg", "R:R", "Shariah", "Matched"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-ink-800">
                  {res.results.map((r) => (
                    <tr key={`${r.exchange}-${r.ticker}`} className="hover:bg-ink-850">
                      <td className="px-4 py-2.5">
                        <Link to={`/stocks/${r.exchange}/${encodeURIComponent(r.ticker)}`} className="font-medium hover:text-brand-500">{r.ticker}</Link>
                        <p className="max-w-[180px] truncate text-[11px] text-ink-400">{r.name}</p>
                      </td>
                      <td className="num px-4 py-2.5">{fmtMoney(r.close, r.currency)}</td>
                      <td className="px-4 py-2.5 text-xs text-ink-300">{fmtDate(r.as_of)}</td>
                      <td className="px-4 py-2.5"><SignalBadge type={r.signal} /></td>
                      <td className="num px-4 py-2.5">{r.score === null ? "n/a" : r.score.toFixed(0)}</td>
                      <td className="num px-4 py-2.5">{fmtNum(r.rsi, 1)}</td>
                      <td className="px-4 py-2.5 text-xs text-ink-300">{r.trend ?? "n/a"}</td>
                      <td className="num px-4 py-2.5">{r.volume_ratio === null ? "n/a" : `${fmtNum(r.volume_ratio, 2)}×`}</td>
                      <td className="num px-4 py-2.5">{r.risk_reward === null ? "n/a" : `${r.risk_reward.toFixed(2)} : 1`}</td>
                      <td className="px-4 py-2.5"><ShariahBadge status={r.shariah} /></td>
                      <td className="px-4 py-2.5 text-[11px] text-ink-400">{r.matched.join(", ") || "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-6 text-[11px] text-ink-500">{res.note} Shariah status uses {res.methodology}.</p>
        </Card>
      )}
    </div>
  );
}
