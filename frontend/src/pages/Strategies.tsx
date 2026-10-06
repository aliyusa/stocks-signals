import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { ExitConfig, StrategyCatalogue, StrategyRow } from "../lib/types";
import { btnPrimary, btnSecondary, inputCls } from "../components/ShariahPanel";
import { Card } from "../components/ui";

type Draft = Omit<StrategyRow, "id" | "is_builtin" | "is_active" | "created_at">;

function Editor({ cat, initial, onSave, onCancel, busy, error }: {
  cat: StrategyCatalogue; initial: Draft; onSave: (d: Draft) => void; onCancel: () => void; busy: boolean; error: string | null;
}) {
  const [d, setD] = useState<Draft>(initial);
  const setExit = (patch: Partial<ExitConfig>) => setD({ ...d, exit: { ...d.exit, ...patch } });
  const toggleRule = (id: string) => setD({ ...d, disabled: d.disabled.includes(id) ? d.disabled.filter((x) => x !== id) : [...d.disabled, id] });
  const byCat = Object.keys(cat.categories).map((c) => ({ c, rules: cat.rules.filter((r) => r.category === c) }));
  return (
    <form className="mt-4 space-y-5 border-t border-ink-800 pt-4" onSubmit={(e) => { e.preventDefault(); onSave(d); }}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-[11px] text-ink-400">Name<input className={inputCls} minLength={2} maxLength={120} required value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
        <label className="text-[11px] text-ink-400 sm:col-span-2">Description<input className={inputCls} maxLength={1000} value={d.description ?? ""} onChange={(e) => setD({ ...d, description: e.target.value })} /></label>
      </div>
      <fieldset>
        <legend className="mb-2 text-[11px] uppercase tracking-wider text-ink-500">Rules and category weights</legend>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {byCat.map(({ c, rules }) => (
            <div key={c} className="rounded-lg border border-ink-800 p-3">
              <label className="block text-xs">
                <span className="flex justify-between text-ink-100"><span>{cat.categories[c]}</span><span className="num">weight {d.weights[c] ?? 0}</span></span>
                <input type="range" min={0} max={50} value={d.weights[c] ?? 0} onChange={(e) => setD({ ...d, weights: { ...d.weights, [c]: Number(e.target.value) } })}
                  className="mt-1 w-full accent-teal-500" aria-label={`${cat.categories[c]} weight`} />
              </label>
              <ul className="mt-2 space-y-1">
                {rules.map((r) => (
                  <li key={r.id}><label className="inline-flex items-center gap-2 text-xs text-ink-300">
                    <input type="checkbox" className="accent-teal-500" checked={!d.disabled.includes(r.id)} onChange={() => toggleRule(r.id)} />{r.label}
                  </label></li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-1 text-[10px] text-ink-500">A switched-off rule stays visible on stock pages but carries no weight. A category with weight 0 or no rules on is left out of the score.</p>
      </fieldset>
      <fieldset>
        <legend className="mb-2 text-[11px] uppercase tracking-wider text-ink-500">Thresholds</legend>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {cat.params.map((p) => (
            <label key={p.key} className="text-[11px] text-ink-400">{p.label}
              <input className={`${inputCls} num`} type="number" step="any" min={p.min} max={p.max} value={d.params[p.key] ?? p.default}
                onChange={(e) => setD({ ...d, params: { ...d.params, [p.key]: Number(e.target.value) } })} />
              <span className="text-[10px] text-ink-500">{p.min} to {p.max} · default {p.default}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className="mb-2 text-[11px] uppercase tracking-wider text-ink-500">Backtest entries and exits</legend>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <label className="text-[11px] text-ink-400">Enter on
            <select className={inputCls} value={d.entry_on.join(",")} onChange={(e) => setD({ ...d, entry_on: e.target.value.split(",") })}>
              <option value="BUY_SETUP">POTENTIAL BUY SETUP</option><option value="BUY_SETUP,WATCHLIST">BUY SETUP or WATCHLIST</option>
            </select>
          </label>
          <label className="text-[11px] text-ink-400">Stop
            <select className={inputCls} value={d.exit.stop} onChange={(e) => setExit({ stop: e.target.value as ExitConfig["stop"] })}>
              <option value="signal">Setup's stop level</option><option value="atr">Entry − ATR multiple</option>
            </select>
          </label>
          {d.exit.stop === "atr" && <label className="text-[11px] text-ink-400">ATR multiple<input className={`${inputCls} num`} type="number" step="0.1" min={0.5} max={10} value={d.exit.stop_atr} onChange={(e) => setExit({ stop_atr: Number(e.target.value) })} /></label>}
          <label className="text-[11px] text-ink-400">Target
            <select className={inputCls} value={d.exit.target} onChange={(e) => setExit({ target: e.target.value as ExitConfig["target"] })}>
              <option value="signal">Setup's Target 1</option><option value="r_multiple">R multiple of the risk</option><option value="none">No target</option>
            </select>
          </label>
          {d.exit.target === "r_multiple" && <label className="text-[11px] text-ink-400">R multiple<input className={`${inputCls} num`} type="number" step="0.1" min={0.5} max={20} value={d.exit.target_r} onChange={(e) => setExit({ target_r: Number(e.target.value) })} /></label>}
          <label className="text-[11px] text-ink-400">Max holding (sessions, 0 = none)<input className={`${inputCls} num`} type="number" min={0} max={1000} value={d.exit.max_hold_days} onChange={(e) => setExit({ max_hold_days: Number(e.target.value) })} /></label>
        </div>
        <div className="mt-2 flex flex-wrap gap-4">
          {Object.entries(cat.exit_checks).map(([k, l]) => (
            <label key={k} className="inline-flex items-center gap-2 text-xs text-ink-300">
              <input type="checkbox" className="accent-teal-500" checked={d.exit.exit_on.includes(k)}
                onChange={() => setExit({ exit_on: d.exit.exit_on.includes(k) ? d.exit.exit_on.filter((x) => x !== k) : [...d.exit.exit_on, k] })} />
              Exit at the next open on: {l}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={btnPrimary} disabled={busy}>Save strategy</button>
        <button type="button" className={btnSecondary} onClick={onCancel}>Cancel</button>
        {error && <span role="alert" className="text-xs text-red-400">{error}</span>}
      </div>
    </form>
  );
}

export default function Strategies() {
  const qc = useQueryClient();
  const cat = useQuery({ queryKey: ["strategy-catalogue"], queryFn: () => api<StrategyCatalogue>("/api/strategies/catalogue"), staleTime: Infinity });
  const q = useQuery({ queryKey: ["strategies"], queryFn: () => api<{ strategies: StrategyRow[]; active_id: number }>("/api/strategies") });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [seed, setSeed] = useState<Draft | null>(null);
  const refresh = () => { for (const k of ["strategies", "analysis", "signals", "scoring", "dashboard"]) qc.invalidateQueries({ queryKey: [k] }); };
  const save = useMutation({
    mutationFn: (d: Draft) => editing === "new"
      ? api("/api/strategies", { method: "POST", body: JSON.stringify(d) })
      : api(`/api/strategies/${editing}`, { method: "PUT", body: JSON.stringify(d) }),
    onSuccess: () => { setEditing(null); refresh(); },
  });
  const activate = useMutation({ mutationFn: (id: number) => api(`/api/strategies/${id}/activate`, { method: "POST" }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/strategies/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const draftOf = (s: StrategyRow, copy: boolean): Draft => ({
    name: copy ? `${s.name} (copy)`.slice(0, 120) : s.name, description: s.description, weights: { ...s.weights }, params: { ...s.params },
    disabled: [...s.disabled], entry_on: [...s.entry_on], exit: { ...s.exit },
  });
  const err = (save.error ?? activate.error ?? del.error) as Error | null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Strategies</h1>
        <p className="text-xs text-ink-400">A strategy chooses which rules count, their weights and thresholds, and how a backtest enters and exits. The active strategy drives signals across the platform. <Link to="/backtesting" className="text-brand-500">Test one on stored history</Link>.</p>
      </div>
      {err && <p role="alert" className="text-xs text-red-400">{err.message}</p>}
      {q.data?.strategies.map((s) => (
        <Card key={s.id} title={<span className="flex flex-wrap items-center gap-2">{s.name}{s.is_active && <span className="rounded bg-brand-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-brand-500">Active</span>}{s.is_builtin && <span className="text-[10px] uppercase text-ink-500">Built-in</span>}</span>}
          action={
            <div className="flex flex-wrap gap-2">
              {!s.is_active && <button className={btnSecondary} onClick={() => activate.mutate(s.id)}>Use for signals</button>}
              <button className={btnSecondary} onClick={() => { setSeed(draftOf(s, true)); setEditing("new"); }}>Copy</button>
              {!s.is_builtin && <button className={btnSecondary} onClick={() => { setSeed(draftOf(s, false)); setEditing(s.id); }}>Edit</button>}
              {!s.is_builtin && <button className={btnSecondary} onClick={() => { if (confirm(`Delete "${s.name}" and its backtests?`)) del.mutate(s.id); }}>Delete</button>}
            </div>
          }>
          {s.description && <p className="mb-2 text-xs text-ink-400">{s.description}</p>}
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
            {Object.entries(s.weights).map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-ink-500">{cat.data?.categories[k] ?? k}</dt><dd className="num">{v}</dd></div>)}
          </dl>
          <p className="mt-2 text-[11px] text-ink-500">
            BUY SETUP at {s.params.buy_score}+ · WATCHLIST at {s.params.watch_score}+ · min R:R {s.params.min_rr} · rules off: {s.disabled.length ? s.disabled.map((d) => cat.data?.rules.find((r) => r.id === d)?.label ?? d).join(", ") : "none"} ·
            stop {s.exit.stop === "atr" ? `${s.exit.stop_atr} × ATR` : "setup level"} · target {s.exit.target === "r_multiple" ? `${s.exit.target_r} R` : s.exit.target === "none" ? "none" : "Target 1"} · max {s.exit.max_hold_days || "no"} sessions
          </p>
          {editing === s.id && cat.data && seed && <Editor cat={cat.data} initial={seed} onSave={(d) => save.mutate(d)} onCancel={() => setEditing(null)} busy={save.isPending} error={save.error ? (save.error as Error).message : null} />}
        </Card>
      ))}
      {editing === "new" && cat.data && seed && (
        <Card title="New strategy"><Editor cat={cat.data} initial={seed} onSave={(d) => save.mutate(d)} onCancel={() => setEditing(null)} busy={save.isPending} error={save.error ? (save.error as Error).message : null} /></Card>
      )}
      <p className="text-[11px] text-ink-500">The "My scoring weights" strategy is the one edited under Settings. Past results do not predict future returns.</p>
    </div>
  );
}
