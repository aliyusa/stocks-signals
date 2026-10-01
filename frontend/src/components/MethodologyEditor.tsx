import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Methodology, Vocabulary } from "../lib/types";
import { btnPrimary, btnSecondary, inputCls } from "./ShariahPanel";
import { Card } from "./ui";

const fmt = (v: number) => `${+(v * 100).toFixed(2)}%`;

function Editor({ m, vocab, onDone }: { m: Methodology; vocab: Vocabulary; onDone: () => void }) {
  const [name, setName] = useState(m.name);
  const [description, setDescription] = useState(m.description);
  const [denominator, setDenominator] = useState(m.denominator);
  const [maxAge, setMaxAge] = useState(m.max_data_age_days);
  const [prohibited, setProhibited] = useState<string[]>(m.prohibited_activities);
  // thresholds are edited as percentages; an empty box means the test is not used
  const [th, setTh] = useState<Record<string, string>>(
    Object.fromEntries(vocab.thresholds.map((t) => [t.key, m.thresholds[t.key] === undefined ? "" : String(+(m.thresholds[t.key] * 100).toFixed(4))])));
  const save = useMutation({
    mutationFn: () => api(`/api/shariah/methodologies/${m.id}`, {
      method: "PUT",
      body: JSON.stringify({
        name, description, denominator, max_data_age_days: maxAge, prohibited_activities: prohibited,
        thresholds: Object.fromEntries(Object.entries(th).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v) / 100])),
      }),
    }),
    onSuccess: onDone,
  });
  return (
    <form className="mt-4 space-y-4 border-t border-ink-800 pt-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-[11px] text-ink-400">Name<input className={inputCls} minLength={3} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="text-[11px] text-ink-400">Denominator for balance-sheet ratios
          <select className={inputCls} value={denominator} onChange={(e) => setDenominator(e.target.value)}>
            {vocab.denominators.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
        </label>
        <label className="text-[11px] text-ink-400">Maximum age of fundamentals (days)
          <input className={`${inputCls} num`} type="number" min={30} max={730} value={maxAge} onChange={(e) => setMaxAge(Number(e.target.value))} />
        </label>
      </div>
      <label className="block text-[11px] text-ink-400">Description<textarea className={`${inputCls} h-16`} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <fieldset>
        <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Limits (%). Leave a box empty to drop that test</legend>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {vocab.thresholds.map((t) => (
            <label key={t.key} className="text-[11px] text-ink-400">{t.label}
              <input className={`${inputCls} num`} type="number" min={0.01} max={99.99} step="any" value={th[t.key]}
                required={t.key === "non_permissible_income_to_revenue"} onChange={(e) => setTh({ ...th, [t.key]: e.target.value })} />
            </label>
          ))}
        </div>
        <p className="mt-1 text-[10px] text-ink-500">The questionable margin marks a ratio as "near limit" when it is within that share of its limit, for example 10% of a 30% limit means 27% or more.</p>
      </fieldset>
      <fieldset>
        <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Excluded business activities</legend>
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {vocab.prohibited.map((p) => (
            <label key={p.tag} className="inline-flex items-center gap-2 text-xs text-ink-300">
              <input type="checkbox" className="accent-teal-500" checked={prohibited.includes(p.tag)}
                onChange={() => setProhibited(prohibited.includes(p.tag) ? prohibited.filter((x) => x !== p.tag) : [...prohibited, p.tag])} />
              {p.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={btnPrimary} disabled={save.isPending}>Save methodology</button>
        <button type="button" className={btnSecondary} onClick={onDone}>Cancel</button>
        {save.isError && <span role="alert" className="text-xs text-red-400">{(save.error as Error).message}</span>}
      </div>
    </form>
  );
}

export default function MethodologyEditor() {
  const qc = useQueryClient();
  const meths = useQuery({ queryKey: ["methodologies"], queryFn: () => api<Methodology[]>("/api/shariah/methodologies") });
  const vocab = useQuery({ queryKey: ["shariah-vocab"], queryFn: () => api<Vocabulary>("/api/shariah/vocabulary"), staleTime: Infinity });
  const [editing, setEditing] = useState<number | null>(null);
  const refresh = () => {
    setEditing(null);
    for (const k of ["methodologies", "shariah", "shariah-screener", "analysis", "signals", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const clone = useMutation({
    mutationFn: (m: Methodology) => api<Methodology>("/api/shariah/methodologies", { method: "POST", body: JSON.stringify({ from_id: m.id, name: `${m.name.replace(/\s*\(default\)/i, "")} (my copy)`.slice(0, 120) }) }),
    onSuccess: (m) => { refresh(); setEditing(m.id); },
  });
  const setDefault = useMutation({ mutationFn: (id: number) => api("/api/shariah/default", { method: "PUT", body: JSON.stringify({ methodology_id: id }) }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/shariah/methodologies/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const label = (k: string) => vocab.data?.thresholds.find((t) => t.key === k)?.label ?? k.replace(/_/g, " ");
  const denom = (k: string) => vocab.data?.denominators.find((d) => d.key === k)?.label ?? k;
  const err = clone.error ?? setDefault.error ?? del.error;

  return (
    <Card title="Shariah methodologies">
      <p className="mb-4 text-xs leading-relaxed text-ink-400">
        The default methodology drives the status shown on stock pages, the scanner, signals and the dashboard. Built-in methodologies
        cannot be edited; make a copy to change limits, the denominator or the excluded activities. Every change is written to the audit log.
      </p>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {meths.data?.map((m) => (
          <div key={m.id} className={`rounded-lg border p-4 ${m.is_default ? "border-brand-600/60" : "border-ink-800"} ${editing === m.id ? "lg:col-span-2" : ""}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold">{m.name}</p>
              <span className="text-[10px] uppercase tracking-wider text-ink-500">{m.is_default ? "Default · " : ""}{m.is_builtin ? "Built-in" : "Custom"}</span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-400">{m.description}</p>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-ink-500">Denominator</dt><dd>{denom(m.denominator)}</dd>
              {Object.entries(m.thresholds).map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-ink-500">{label(k)}</dt><dd className="num">{k === "questionable_margin" ? fmt(v) : `< ${fmt(v)}`}</dd></div>
              ))}
              <dt className="text-ink-500">Max data age</dt><dd>{m.max_data_age_days} days</dd>
            </dl>
            <p className="mt-3 text-[11px] text-ink-500">Excluded: {m.prohibited_activities.map((a) => vocab.data?.prohibited.find((p) => p.tag === a)?.label ?? a).join("; ")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {!m.is_default && <button className={btnSecondary} onClick={() => setDefault.mutate(m.id)} disabled={setDefault.isPending}>Make default</button>}
              <button className={btnSecondary} onClick={() => clone.mutate(m)} disabled={clone.isPending}>Copy</button>
              {m.owned && editing !== m.id && <button className={btnSecondary} onClick={() => setEditing(m.id)}>Edit</button>}
              {m.owned && <button className={btnSecondary} onClick={() => { if (confirm(`Delete "${m.name}"? Past screens made with it are deleted too.`)) del.mutate(m.id); }}>Delete</button>}
            </div>
            {editing === m.id && vocab.data && <Editor m={m} vocab={vocab.data} onDone={refresh} />}
          </div>
        ))}
      </div>
      {err && <p role="alert" className="mt-3 text-xs text-red-400">{(err as Error).message}</p>}
      <p className="mt-4 text-[11px] text-ink-500">Methodologies differ between scholars and index providers. Verify compliance with a qualified Shariah scholar or a recognised screening provider.</p>
    </Card>
  );
}
