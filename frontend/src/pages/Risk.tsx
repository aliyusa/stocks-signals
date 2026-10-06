import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum } from "../lib/format";
import type { RiskResult } from "../lib/types";
import { inputCls } from "../components/ShariahPanel";
import { Card, Stat } from "../components/ui";

const FIELDS: [string, string, string][] = [
  ["account", "Account size", "Cash you are prepared to invest"],
  ["risk_pct", "Risk per trade (%)", "Commonly 0.5% to 2%"],
  ["entry", "Entry price", ""],
  ["stop", "Stop price", "Below the entry"],
  ["target", "Target price (optional)", ""],
  ["cost_pct_per_side", "Costs per side (%)", "NGX: about 2% with a typical broker"],
  ["lot_size", "Lot size (shares)", "Smallest tradable quantity"],
  ["max_position_pct", "Maximum position (% of account)", "Caps concentration"],
];

function savedAccount(): string {
  try { return localStorage.getItem("hss.account") ?? "1000000"; } catch { return "1000000"; }
}

export default function Risk() {
  const [qs] = useSearchParams();
  const [f, setF] = useState<Record<string, string>>({
    account: savedAccount(), risk_pct: "1", entry: qs.get("entry") ?? "", stop: qs.get("stop") ?? "",
    target: qs.get("target") ?? "", cost_pct_per_side: qs.get("mic") === "XNSA" ? "2" : "0", lot_size: "1", max_position_pct: "25",
  });
  const cur = qs.get("currency") ?? "";
  const calc = useMutation({
    mutationFn: () => api<RiskResult>("/api/risk/position-size", {
      method: "POST",
      body: JSON.stringify({
        account: Number(f.account), risk_pct: Number(f.risk_pct), entry: Number(f.entry), stop: Number(f.stop),
        target: f.target === "" ? null : Number(f.target), cost_pct_per_side: Number(f.cost_pct_per_side || 0),
        lot_size: Math.max(1, Math.floor(Number(f.lot_size || 1))), max_position_pct: Number(f.max_position_pct || 100),
      }),
    }),
  });
  const ready = Number(f.account) > 0 && Number(f.entry) > 0 && Number(f.stop) > 0 && Number(f.risk_pct) > 0;
  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem("hss.account", f.account); } catch { /* storage unavailable */ }
    const t = setTimeout(() => calc.mutate(), 300);
    return () => clearTimeout(t);
  }, [JSON.stringify(f)]); // eslint-disable-line react-hooks/exhaustive-deps
  const r = calc.data;
  const m = (v: number | undefined) => (v === undefined ? "n/a" : `${cur ? cur + " " : ""}${fmtNum(v, 2)}`);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Risk Calculator</h1>
        <p className="text-xs text-ink-400">
          How many shares to buy so that a fall to your stop, after costs on both sides, loses no more than your chosen share of the account.
          {qs.get("ticker") && <> Prefilled from <Link className="text-brand-500" to={`/stocks/${qs.get("mic")}/${qs.get("ticker")}`}>{qs.get("ticker")}</Link>'s setup levels.</>}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Inputs">
          <div className="grid grid-cols-2 gap-3">
            {FIELDS.map(([k, l, hint]) => (
              <label key={k} className="text-[11px] text-ink-400">{l}
                <input className={`${inputCls} num`} type="number" step="any" min={0} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
                {hint && <span className="mt-0.5 block text-[10px] text-ink-500">{hint}</span>}
              </label>
            ))}
          </div>
        </Card>
        <div className="space-y-4 lg:col-span-2">
          {!ready ? <Card><p className="text-sm text-ink-400">Enter the account size, risk, entry and stop.</p></Card> : r && !r.ok ? (
            <Card><ul className="space-y-1">{r.errors?.map((e) => <li key={e} role="alert" className="text-sm text-red-400">{e}</li>)}</ul></Card>
          ) : r ? (
            <>
              <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
                <Stat label="Shares" value={fmtNum(r.shares, 0)} hint={r.capped_by ? `Capped by the ${r.capped_by}` : "Rounded down to the lot size"} />
                <Stat label="Position value" value={m(r.position_value)} hint={`${fmtNum(r.position_pct, 1)}% of the account`} />
                <Stat label="Loss at the stop" value={m(r.loss_at_stop)} hint={`${fmtNum(r.loss_at_stop_pct, 2)}% of the account, costs included`} />
                <Stat label="Reward : risk" value={r.reward_risk == null ? "n/a" : `${fmtNum(r.reward_risk, 2)} : 1`} hint={r.gain_at_target != null ? `Gain at target ${m(r.gain_at_target)}` : "Add a target"} />
              </div>
              <Card title="How it was calculated">
                <ol className="list-decimal space-y-1 pl-5 text-xs text-ink-300">{r.steps?.map((s) => <li key={s} className="num">{s}</li>)}</ol>
                <p className="mt-3 text-[11px] text-ink-500">The stop is {fmtNum(r.stop_distance_pct, 2)}% below the entry. Entry costs are {m(r.entry_costs)}. A gap below the stop can lose more than planned.</p>
                {!!r.warnings?.length && <ul className="mt-3 space-y-1">{r.warnings.map((w) => <li key={w} className="flex gap-1.5 text-xs text-amber-300"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{w}</li>)}</ul>}
              </Card>
            </>
          ) : <Card><p className="text-sm text-ink-400">Calculating…</p></Card>}
          <p className="text-[11px] text-ink-500">A sizing aid, not advice. The platform never places orders.</p>
        </div>
      </div>
    </div>
  );
}
