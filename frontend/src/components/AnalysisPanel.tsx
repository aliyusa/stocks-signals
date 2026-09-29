import { AlertTriangle, Check, Minus, X } from "lucide-react";
import type { SignalResult } from "../lib/types";
import { fmtCompact, fmtDate, fmtMoney, fmtNum } from "../lib/format";
import { SignalBadge } from "./badges";
import { Card } from "./ui";

const n = (v: unknown, d = 2) => (typeof v === "number" ? fmtNum(v, d) : "n/a");

function RuleIcon({ passed }: { passed: boolean | null }) {
  if (passed === true) return <Check size={14} className="text-emerald-400" aria-label="Passed" />;
  if (passed === false) return <X size={14} className="text-red-400" aria-label="Failed" />;
  return <Minus size={14} className="text-ink-500" aria-label="Not evaluated" />;
}

export function SignalSummary({ s, currency, strategy }: { s: SignalResult; currency: string | null; strategy: string }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <SignalBadge type={s.signal_type} />
        <p className="num text-2xl font-semibold">{s.score === null ? "n/a" : s.score.toFixed(0)}<span className="text-sm text-ink-400">/100 setup score</span></p>
      </div>
      <p className="text-xs text-ink-400">
        Coverage {Math.round(s.coverage * 100)}% of the scoring weight · Close of {fmtDate(s.as_of)} · {fmtMoney(s.close, currency)} · Strategy: {strategy}
      </p>
      <p className="text-sm leading-relaxed text-ink-300">{s.summary}</p>
      {s.reasons.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-300">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      )}
      <p className="text-[11px] leading-relaxed text-ink-500">
        The setup score is the weighted share of rules that passed. It is not a probability of profit.
      </p>
    </div>
  );
}

export function LevelsTable({ s, currency }: { s: SignalResult; currency: string | null }) {
  const rows: { name: string; price: number | null; method: string }[] = [];
  const entryNote = s.level_notes.find((l) => l.name.toLowerCase().startsWith("entry"));
  const stopNote = s.level_notes.find((l) => l.name.toLowerCase().startsWith("stop"));
  rows.push({ name: "Entry zone low", price: s.entry_low, method: entryNote?.method ?? "" });
  rows.push({ name: "Entry zone high", price: s.entry_high, method: entryNote?.method ?? "" });
  rows.push({ name: "Invalidation (stop)", price: s.stop, method: stopNote?.method ?? "" });
  s.targets.forEach((t) => rows.push(t));
  for (const l of s.level_notes) if (!rows.some((r) => r.name === l.name) && l !== entryNote && l !== stopNote) rows.push(l);
  return (
    <div className="space-y-3">
      <div className="-mx-4 overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
            <tr><th className="px-4 py-2 font-medium">Level</th><th className="px-4 py-2 text-right font-medium">Price</th><th className="px-4 py-2 font-medium">How it was derived</th></tr>
          </thead>
          <tbody className="divide-y divide-ink-800">
            {rows.map((r) => (
              <tr key={r.name}>
                <td className="px-4 py-2 text-ink-300">{r.name}</td>
                <td className="num px-4 py-2 text-right">{r.price === null ? "Not defined" : fmtMoney(r.price, currency)}</td>
                <td className="px-4 py-2 text-xs text-ink-400">{r.method || "n/a"}</td>
              </tr>
            ))}
            <tr>
              <td className="px-4 py-2 text-ink-300">Reward : risk (Target 1)</td>
              <td className="num px-4 py-2 text-right">{s.risk_reward === null ? "Not stated" : `${s.risk_reward.toFixed(2)} : 1`}</td>
              <td className="px-4 py-2 text-xs text-ink-400">(Target 1 − entry midpoint) ÷ (entry midpoint − stop)</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <p className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Support (swing clusters)</p>
          {s.supports.length ? s.supports.map((x) => <p key={x.price} className="num text-ink-300">{fmtMoney(x.price, currency)} · {x.touches} touch{x.touches > 1 ? "es" : ""}</p>) : <p className="text-ink-500">None found</p>}
        </div>
        <div>
          <p className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Resistance (swing clusters)</p>
          {s.resistances.length ? s.resistances.map((x) => <p key={x.price} className="num text-ink-300">{fmtMoney(x.price, currency)} · {x.touches} touch{x.touches > 1 ? "es" : ""}</p>) : <p className="text-ink-500">None found</p>}
        </div>
      </div>
      <p className="text-[11px] text-ink-500">
        Levels come from price structure and ATR only. A target is never invented where the chart shows no structure.
        {s.signal_type !== "BUY_SETUP" && " These levels are for reference: the rules do not currently support a setup, so they are not an entry plan."}
      </p>
    </div>
  );
}

export function Breakdown({ s }: { s: SignalResult }) {
  const cats = Object.entries(s.breakdown);
  return (
    <div className="space-y-5">
      <ul className="space-y-2.5">
        {cats.map(([k, c]) => {
          const pct = c.pct === null ? null : Math.round(c.pct * 100);
          return (
            <li key={k}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="text-ink-300">{c.label} <span className="text-ink-500">· weight {c.weight}</span></span>
                <span className="num text-ink-100">
                  {pct === null ? "not evaluated" : `${c.passed}/${c.evaluated} rules · ${fmtNum(c.points, 1)} pts`}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded bg-ink-800" aria-hidden>
                <div className="h-full rounded bg-brand-500" style={{ width: `${pct ?? 0}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wider text-ink-500">Every rule</p>
        <ul className="divide-y divide-ink-800 text-xs">
          {s.rules.map((r) => (
            <li key={r.id} className="flex gap-2 py-1.5">
              <span className="mt-0.5"><RuleIcon passed={r.passed} /></span>
              <div className="min-w-0 flex-1">
                <p className="text-ink-100">{r.label} <span className="text-ink-500">· {s.breakdown[r.category]?.label ?? r.category}</span></p>
                {(r.detail || r.value) && <p className="text-ink-400">{r.detail || r.value}</p>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function Warnings({ s }: { s: SignalResult }) {
  if (!s.warnings.length) return <p className="text-xs text-ink-400">No warnings.</p>;
  return (
    <ul className="space-y-1.5">
      {s.warnings.map((w) => (
        <li key={w} className="flex gap-1.5 text-xs leading-snug text-amber-300"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{w}</li>
      ))}
    </ul>
  );
}

export function Timeframes({ s }: { s: SignalResult }) {
  const tf = s.timeframes;
  const rg = s.snapshot.regime;
  return (
    <div className="space-y-3 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        {["15m", "1h", "4h", "daily", "weekly"].map((k) => (
          <div key={k} className="contents">
            <dt className="text-ink-500">{k === "daily" ? "Daily" : k === "weekly" ? "Weekly" : k}</dt>
            <dd className={tf[k]?.startsWith("Data unavailable") ? "text-ink-500" : "text-ink-100"}>{tf[k] ?? "n/a"}</dd>
          </div>
        ))}
      </dl>
      <p className="text-ink-300">{tf.agreement}</p>
      <div className="rounded-lg border border-ink-800 p-2.5">
        <p className="text-[11px] uppercase tracking-wider text-ink-500">Market regime</p>
        {rg && rg.label ? (
          <p className="mt-1 text-ink-300"><span className="font-medium text-ink-100">{rg.label}</span>{rg.volatility ? ` · ${rg.volatility}` : ""}. {rg.explanation} {rg.index ? `(${rg.index}, ${fmtDate(rg.as_of)})` : ""}</p>
        ) : (
          <p className="mt-1 text-ink-500">Data unavailable. {rg?.explanation ?? "No index history for this market; the market rule is not scored."}</p>
        )}
      </div>
    </div>
  );
}

export function Snapshot({ s, currency }: { s: SignalResult; currency: string | null }) {
  const sn = s.snapshot;
  const m = (k: string) => (typeof sn[k] === "number" ? fmtMoney(sn[k] as number, currency) : "n/a");
  const items: [string, string][] = [
    ["SMA 20", m("sma20")], ["SMA 50", m("sma50")], ["SMA 200", m("sma200")], ["EMA 21", m("ema21")],
    ["RSI 14", n(sn.rsi, 1)], ["MACD", n(sn.macd, 3)], ["MACD signal", n(sn.macd_signal, 3)], ["ADX 14", n(sn.adx, 1)],
    ["Stochastic %K", n(sn.stoch_k, 1)], ["ROC 10", typeof sn.roc10 === "number" ? `${fmtNum(sn.roc10 as number, 2)}%` : "n/a"],
    ["ATR 14", m("atr")], ["ATR % of price", typeof sn.atr_pct === "number" ? `${fmtNum(sn.atr_pct as number, 2)}%` : "n/a"],
    ["Bollinger upper", m("bb_up")], ["Bollinger lower", m("bb_lo")],
    ["Volume", fmtCompact(sn.volume as number | null)], ["Volume ÷ 20-day avg", typeof sn.volume_ratio === "number" ? `${fmtNum(sn.volume_ratio as number, 2)}×` : "n/a"],
    ["52-week high", m("high_52w")], ["52-week low", m("low_52w")],
    ["Median traded value (20d)", typeof sn.median_traded_value_20 === "number" ? `${currency ?? ""} ${fmtCompact(sn.median_traded_value_20 as number)}` : "n/a"],
    ["Swing structure", String(sn.structure ?? "n/a").replace(/_/g, " ")],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
      {items.map(([k, v]) => (
        <div key={k}><dt className="text-ink-500">{k}</dt><dd className="num text-ink-100">{v}</dd></div>
      ))}
    </dl>
  );
}

export function AnalysisGrid({ s, currency, strategy }: { s: SignalResult; currency: string | null; strategy: string }) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card title="Technical signal" className="lg:col-span-2"><SignalSummary s={s} currency={currency} strategy={strategy} /></Card>
      <Card title="Warnings"><Warnings s={s} /></Card>
      <Card title="Levels" className="lg:col-span-2"><LevelsTable s={s} currency={currency} /></Card>
      <Card title="Timeframes & regime"><Timeframes s={s} /></Card>
      <Card title="Score breakdown" className="lg:col-span-2"><Breakdown s={s} /></Card>
      <Card title="Indicator snapshot"><Snapshot s={s} currency={currency} /></Card>
    </div>
  );
}
