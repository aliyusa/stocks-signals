import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtDateTime, fmtMoney, fmtNum } from "../lib/format";
import type { BacktestResult, BtMetrics, StockRef, StrategyCatalogue, StrategyRow } from "../lib/types";
import EquityChart from "../components/EquityChart";
import { btnPrimary, btnSecondary, inputCls } from "../components/ShariahPanel";
import StockPicker from "../components/StockPicker";
import { Card, EmptyState, Stat } from "../components/ui";

const pct = (v: number | null | undefined, d = 1) => (v == null ? "n/a" : `${v > 0 ? "+" : ""}${fmtNum(v, d)}%`);
const iso = (d: Date) => d.toISOString().slice(0, 10);

function StockResult({ m, currency }: { m: BtMetrics; currency: string }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Strategy return" value={pct(m.total_return_pct)} hint={`${pct(m.annualised_return_pct)} a year`} />
        <Stat label="Buy and hold" value={pct(m.buy_hold_return_pct)} hint={`Max drawdown ${pct(m.buy_hold_max_drawdown_pct)}`} />
        <Stat label="Max drawdown" value={pct(m.max_drawdown_pct)} />
        <Stat label="Trades" value={m.trades} hint={`${m.wins} won · ${m.losses} lost`} />
        <Stat label="Win rate" value={m.win_rate == null ? "n/a" : `${fmtNum(m.win_rate, 0)}%`} hint={`Avg win ${pct(m.avg_gain_pct)} · loss ${pct(m.avg_loss_pct)}`} />
        <Stat label="Profit factor" value={m.profit_factor == null ? "n/a" : fmtNum(m.profit_factor, 2)} hint={`Avg R ${m.avg_r == null ? "n/a" : fmtNum(m.avg_r, 2)} · in market ${fmtNum(m.exposure_pct, 0)}%`} />
      </div>
      <EquityChart points={m.equity} currency={currency} />
      {Object.keys(m.skipped).length > 0 && <p className="text-[11px] text-ink-400">Signals not taken: {Object.entries(m.skipped).map(([k, v]) => `${k} (${v})`).join("; ")}.</p>}
    </div>
  );
}

export default function Backtesting() {
  const qc = useQueryClient();
  const cat = useQuery({ queryKey: ["strategy-catalogue"], queryFn: () => api<StrategyCatalogue>("/api/strategies/catalogue"), staleTime: Infinity });
  const strats = useQuery({ queryKey: ["strategies"], queryFn: () => api<{ strategies: StrategyRow[]; active_id: number }>("/api/strategies") });
  const history = useQuery({ queryKey: ["backtests"], queryFn: () => api<{ backtests: BacktestResult[] }>("/api/backtests") });
  const [sid, setSid] = useState<number | null>(null);
  const [universe, setUniverse] = useState<StockRef[]>([]);
  const [pick, setPick] = useState<StockRef | null>(null);
  const today = new Date();
  const [start, setStart] = useState(iso(new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())));
  const [end, setEnd] = useState(iso(today));
  const [preset, setPreset] = useState("ngx_typical");
  const [sizing, setSizing] = useState("all_in");
  const [riskPct, setRiskPct] = useState("1");
  const [shariah, setShariah] = useState("exclude_non_compliant");
  const [viewId, setViewId] = useState<number | null>(null);
  const [stockIdx, setStockIdx] = useState(0);
  const cost = cat.data?.cost_presets[preset];
  const run = useMutation({
    mutationFn: () => api<BacktestResult>("/api/backtests", {
      method: "POST",
      body: JSON.stringify({
        strategy_id: sid ?? strats.data?.active_id, universe: universe.map((u) => ({ exchange: u.exchange, ticker: u.ticker })),
        start, end, commission_bps: cost?.commission_bps ?? 0, slippage_bps: cost?.slippage_bps ?? 0, sizing,
        risk_pct: Number(riskPct), shariah_filter: shariah,
      }),
    }),
    onSuccess: (b) => { setViewId(b.id); setStockIdx(0); qc.setQueryData(["backtest", b.id], b); qc.invalidateQueries({ queryKey: ["backtests"] }); },
  });
  const view = useQuery({ queryKey: ["backtest", viewId], queryFn: () => api<BacktestResult>(`/api/backtests/${viewId}`), enabled: viewId !== null });
  const b = view.data;
  const ps = b?.metrics?.per_stock ?? [];
  const cur = ps[stockIdx];
  const trades = (b?.trades ?? []).filter((t) => !cur || t.ticker === cur.ticker);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Backtesting</h1>
        <p className="max-w-4xl text-xs text-ink-400">
          Replays a strategy bar by bar on stored daily prices. Each decision uses only data up to that day's close and fills at the next open,
          with costs and slippage on both sides. Uses no EODHD calls. Past results do not predict future returns.
        </p>
      </div>

      <Card title="Set up a test">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (universe.length) run.mutate(); }}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-[11px] text-ink-400">Strategy
              <select className={inputCls} value={sid ?? strats.data?.active_id ?? ""} onChange={(e) => setSid(Number(e.target.value))}>
                {strats.data?.strategies.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_active ? " (active)" : ""}</option>)}
              </select>
            </label>
            <label className="text-[11px] text-ink-400">From<input className={inputCls} type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} /></label>
            <label className="text-[11px] text-ink-400">To<input className={inputCls} type="date" value={end} min={start} max={iso(today)} onChange={(e) => setEnd(e.target.value)} /></label>
            <label className="text-[11px] text-ink-400">Costs
              <select className={inputCls} value={preset} onChange={(e) => setPreset(e.target.value)}>
                {cat.data && Object.entries(cat.data.cost_presets).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              {cost && <span className="text-[10px] text-ink-500">{cost.commission_bps / 100}% fees + {cost.slippage_bps / 100}% slippage per side</span>}
            </label>
            <label className="text-[11px] text-ink-400">Position size
              <select className={inputCls} value={sizing} onChange={(e) => setSizing(e.target.value)}>
                <option value="all_in">All available cash per trade</option><option value="risk_pct">Risk a % of equity to the stop</option>
              </select>
            </label>
            {sizing === "risk_pct" && <label className="text-[11px] text-ink-400">Risk per trade (%)<input className={`${inputCls} num`} type="number" step="0.1" min={0.1} max={10} value={riskPct} onChange={(e) => setRiskPct(e.target.value)} /></label>}
            <label className="text-[11px] text-ink-400">Shariah filter (point in time)
              <select className={inputCls} value={shariah} onChange={(e) => setShariah(e.target.value)}>
                <option value="exclude_non_compliant">Skip entries while NON-COMPLIANT</option>
                <option value="require_compliant">Enter only while COMPLIANT</option>
                <option value="none">No filter</option>
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-64"><StockPicker value={pick} onChange={setPick} label="Add a stock (up to 10)" /></div>
            <button type="button" className={btnSecondary} disabled={!pick || universe.length >= 10 || universe.some((u) => u.exchange === pick?.exchange && u.ticker === pick?.ticker)}
              onClick={() => { if (pick) setUniverse([...universe, pick]); setPick(null); }}>Add</button>
            {universe.map((u) => (
              <span key={`${u.exchange}-${u.ticker}`} className="inline-flex items-center gap-1 rounded-md bg-ink-800 px-2 py-1 text-xs ring-1 ring-ink-700">
                {u.ticker}<button type="button" aria-label={`Remove ${u.ticker}`} onClick={() => setUniverse(universe.filter((x) => x !== u))}><X size={12} /></button>
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className={btnPrimary} disabled={!universe.length || run.isPending}>
              <FlaskConical size={12} className={`mr-1 inline ${run.isPending ? "animate-spin" : ""}`} />{run.isPending ? "Running…" : "Run backtest"}
            </button>
            {run.isError && <span role="alert" className="text-xs text-red-400">{(run.error as Error).message}</span>}
            <span className="text-[11px] text-ink-500">Only stored history is used; open a stock first to store its prices. The free EODHD plan stores about 1 year.</span>
          </div>
        </form>
      </Card>

      {b && b.metrics && (
        <Card title={`${b.strategy} · ${fmtDate(b.start)} to ${fmtDate(b.end)}`} action={<span className="text-[11px] text-ink-400">Run {fmtDateTime(b.created_at)}</span>}>
          <div className="mb-4 flex flex-wrap gap-1" role="tablist" aria-label="Stocks">
            {ps.map((p, i) => (
              <button key={p.ticker} role="tab" aria-selected={stockIdx === i} onClick={() => setStockIdx(i)}
                className={`rounded-md px-3 py-1 text-xs ${stockIdx === i ? "bg-ink-800 text-ink-100 ring-1 ring-ink-700" : "text-ink-400 hover:text-ink-100"}`}>{p.ticker}</button>
            ))}
          </div>
          {cur && !cur.ok ? <p className="text-sm text-amber-300">{cur.ticker}: {cur.error}</p> : cur?.metrics && <StockResult m={cur.metrics} currency={cur.currency} />}
          <h3 className="mb-2 mt-6 text-sm font-semibold">Trades</h3>
          {trades.length === 0 ? <EmptyState title="No trades">The strategy gave no entry in this period, or every entry was filtered out.</EmptyState> : (
            <div className="-mx-4 overflow-x-auto">
              <table className="w-full min-w-[960px] text-xs [&_td]:whitespace-nowrap">
                <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                  <tr>{["Signal", "Entry", "Price", "Shares", "Stop", "Target", "Exit", "Price", "Reason", "Sessions", "R", "P/L"].map((h, i) => <th key={i} className="px-4 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-ink-800">
                  {trades.map((t, i) => (
                    <tr key={i}>
                      <td className="px-4 py-2">{fmtDate(t.signal_date)}<p className="text-[10px] text-ink-500">score {t.score == null ? "n/a" : fmtNum(t.score, 0)}</p></td>
                      <td className="px-4 py-2">{fmtDate(t.entry_date)}</td>
                      <td className="num px-4 py-2">{fmtNum(t.entry, 2)}</td>
                      <td className="num px-4 py-2">{fmtNum(t.shares, 0)}</td>
                      <td className="num px-4 py-2">{fmtNum(t.stop, 2)}</td>
                      <td className="num px-4 py-2">{t.target == null ? "none" : fmtNum(t.target, 2)}</td>
                      <td className="px-4 py-2">{fmtDate(t.exit_date)}</td>
                      <td className="num px-4 py-2">{fmtNum(t.exit, 2)}</td>
                      <td className="px-4 py-2 text-ink-300">{t.reason.replace(/_/g, " ")}</td>
                      <td className="num px-4 py-2">{t.bars_held}</td>
                      <td className="num px-4 py-2">{t.r_multiple == null ? "n/a" : fmtNum(t.r_multiple, 2)}</td>
                      <td className={`num px-4 py-2 ${t.pl >= 0 ? "text-up" : "text-down"}`}>{fmtMoney(t.pl, t.currency)} ({pct(t.pl_pct)})</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <ul className="mt-4 space-y-0.5 text-[11px] text-ink-500">
            {[...(b.metrics.notes ?? []), ...(b.metrics.limitations ?? [])].map((n) => <li key={n}>{n}</li>)}
            {b.universe?.shariah_methodology && <li>Shariah filter used {b.universe.shariah_methodology}.</li>}
          </ul>
        </Card>
      )}

      <Card title="Earlier backtests">
        {!history.data?.backtests.length ? <p className="text-xs text-ink-400">None yet.</p> : (
          <ul className="divide-y divide-ink-800 text-xs">
            {history.data.backtests.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <button className="text-left hover:text-brand-500" onClick={() => { setViewId(h.id); setStockIdx(0); }}>
                  <span className="font-medium text-ink-100">{h.strategy}</span> · {h.stocks.join(", ")} · {fmtDate(h.start)} to {fmtDate(h.end)}
                </button>
                <span className="text-ink-400">{h.summary ? `${h.summary.trades} trades · avg return ${pct(h.summary.avg_total_return_pct)} vs buy and hold ${pct(h.summary.avg_buy_hold_return_pct)}` : ""} · {fmtDateTime(h.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[11px] text-ink-500">The last 50 backtests are kept. <Link to="/strategies" className="text-brand-500">Edit strategies</Link>.</p>
      </Card>
    </div>
  );
}
