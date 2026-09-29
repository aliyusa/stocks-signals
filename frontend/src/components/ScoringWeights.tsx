import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Scoring } from "../lib/types";
import { Card } from "./ui";

export default function ScoringWeights() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["scoring"], queryFn: () => api<Scoring>("/api/scoring") });
  const [w, setW] = useState<Record<string, number>>({});
  useEffect(() => { if (q.data) setW(q.data.weights); }, [q.data]);
  const done = () => {
    qc.invalidateQueries({ queryKey: ["scoring"] });
    qc.invalidateQueries({ queryKey: ["analysis"] });
    qc.invalidateQueries({ queryKey: ["signals"] });
  };
  const save = useMutation({ mutationFn: () => api("/api/scoring", { method: "PUT", body: JSON.stringify({ weights: w }) }), onSuccess: done });
  const reset = useMutation({ mutationFn: () => api("/api/scoring", { method: "DELETE" }), onSuccess: done });

  if (!q.data) return <Card title="Setup score weights"><p className="text-sm text-ink-400">{q.isError ? (q.error as Error).message : "Loading…"}</p></Card>;
  const d = q.data;
  const total = Object.values(w).reduce((a, b) => a + b, 0);
  const dirty = JSON.stringify(w) !== JSON.stringify(d.weights);

  return (
    <Card title="Setup score weights" action={<span className="text-[11px] text-ink-400">{d.custom ? "Custom weights" : "Built-in defaults"}</span>}>
      <p className="mb-4 text-xs leading-relaxed text-ink-400">
        Each category scores the share of its rules that passed, times its weight. The total is rescaled to 100 over the categories
        that could be evaluated, so weights need not add up to 100. Current total: <span className="num text-ink-100">{total}</span>.
      </p>
      <div className="grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
        {Object.keys(d.defaults).map((k) => (
          <label key={k} className="block text-xs">
            <span className="flex justify-between text-ink-300">
              <span>{d.labels[k]}</span>
              <span className="num text-ink-100">{w[k] ?? 0}{w[k] !== d.defaults[k] && <span className="text-ink-500"> (default {d.defaults[k]})</span>}</span>
            </span>
            <input type="range" min={0} max={50} step={1} value={w[k] ?? 0} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })}
              className="mt-1 w-full accent-teal-500" aria-label={`${d.labels[k]} weight`} />
          </label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button onClick={() => save.mutate()} disabled={!dirty || total <= 0 || save.isPending}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-50">Save weights</button>
        <button onClick={() => reset.mutate()} disabled={!d.custom || reset.isPending}
          className="rounded-md bg-ink-800 px-3 py-1.5 text-xs text-ink-100 ring-1 ring-ink-700 hover:bg-ink-700 disabled:opacity-50">Reset to defaults</button>
        {(save.isError || reset.isError) && <span role="alert" className="text-xs text-red-400">{((save.error ?? reset.error) as Error).message}</span>}
        {save.isSuccess && !dirty && <span className="text-xs text-emerald-400">Saved. Signals recompute on next view or scan.</span>}
      </div>
      <details className="mt-4 text-xs text-ink-400">
        <summary className="cursor-pointer text-ink-300">Fixed thresholds</summary>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
          {Object.entries(d.params).map(([k, v]) => (
            <div key={k}><dt className="text-ink-500">{k.replace(/_/g, " ")}</dt><dd className="num text-ink-100">{v}</dd></div>
          ))}
          {Object.entries(d.liquidity_thresholds).map(([c, v]) => (
            <div key={c}><dt className="text-ink-500">min median traded value ({c})</dt><dd className="num text-ink-100">{c} {v.toLocaleString("en-GB")}</dd></div>
          ))}
        </dl>
      </details>
    </Card>
  );
}
