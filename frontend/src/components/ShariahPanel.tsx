import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CircleHelp, Minus, Plus, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtCompact, fmtDate, fmtDateTime, fmtMoney, fmtNum } from "../lib/format";
import type {
  Activity, ExternalOpinion, FundamentalsRow, RatioResult, StockShariah, TestResult, Vocabulary,
} from "../lib/types";
import { ShariahBadge } from "./badges";
import { Card, EmptyState } from "./ui";

export const inputCls = "mt-1 w-full rounded-md border border-ink-700 bg-ink-950 px-2 py-1.5 text-sm text-ink-100";
export const btnPrimary = "rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-50";
export const btnSecondary = "rounded-md bg-ink-800 px-3 py-1.5 text-xs text-ink-100 ring-1 ring-ink-700 hover:bg-ink-700 disabled:opacity-50";
const PERIOD: Record<string, string> = { A: "Year", H: "Half-year", Q: "Quarter", TTM: "12 months" };
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "n/a" : `${fmtNum(v * 100, d)}%`);

const RESULT: Record<TestResult, { label: string; cls: string; Icon: typeof Check; bar: string }> = {
  pass: { label: "Pass", cls: "text-emerald-300 bg-emerald-500/10 ring-emerald-500/30", Icon: Check, bar: "bg-emerald-500" },
  near: { label: "Near limit", cls: "text-amber-300 bg-amber-500/10 ring-amber-500/30", Icon: AlertTriangle, bar: "bg-amber-500" },
  questionable: { label: "Uncertain", cls: "text-amber-300 bg-amber-500/10 ring-amber-500/30", Icon: CircleHelp, bar: "bg-amber-500" },
  fail: { label: "Fail", cls: "text-red-300 bg-red-500/10 ring-red-500/30", Icon: X, bar: "bg-red-500" },
  insufficient: { label: "Missing data", cls: "text-ink-300 bg-ink-800 ring-ink-700", Icon: Minus, bar: "bg-ink-600" },
};

export function ResultChip({ r }: { r: TestResult }) {
  const { label, cls, Icon } = RESULT[r];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${cls}`}>
      <Icon size={12} aria-hidden /> {label}
    </span>
  );
}

function Meter({ r }: { r: RatioResult }) {
  // Scale runs to 1.5 × the threshold (or the value, if larger) so the limit sits at a fixed, readable position.
  const max = Math.max(r.threshold * 1.5, r.value ?? 0);
  const w = r.value === null ? 0 : Math.min(100, (r.value / max) * 100);
  const t = (r.threshold / max) * 100;
  return (
    <div className="relative mt-2 h-2 rounded bg-ink-800" role="img"
      aria-label={`${r.label}: ${pct(r.value)} against a limit of ${pct(r.threshold, 0)}`}>
      <div className={`h-full rounded ${RESULT[r.result].bar}`} style={{ width: `${w}%` }} />
      <div className="absolute -top-1 h-4 w-0.5 bg-ink-100" style={{ left: `calc(${t}% - 1px)` }} title={`Limit ${pct(r.threshold, 0)}`} />
    </div>
  );
}

function Ratios({ ratios, currency }: { ratios: RatioResult[]; currency: string | null }) {
  if (!ratios.length) return <p className="text-xs text-ink-400">This methodology defines no ratio tests.</p>;
  return (
    <ul className="space-y-5">
      {ratios.map((r) => (
        <li key={r.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm text-ink-100">{r.label} ÷ {r.denominator.name.toLowerCase()}</p>
            <div className="flex items-center gap-2">
              <span className="num text-sm text-ink-100">{pct(r.value)}</span>
              <span className="text-[11px] text-ink-400">limit {"<"} {pct(r.threshold, 0)}</span>
              <ResultChip r={r.result} />
            </div>
          </div>
          <Meter r={r} />
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-2">
            <div><dt className="inline text-ink-500">Numerator: </dt>
              <dd className="inline text-ink-300"><span className="num text-ink-100">{r.numerator.value === null ? "n/a" : fmtMoney(r.numerator.value, currency)}</span> · {r.numerator.note}</dd></div>
            <div><dt className="inline text-ink-500">{r.denominator.name}: </dt>
              <dd className="inline text-ink-300"><span className="num text-ink-100">{r.denominator.value === null ? "n/a" : fmtMoney(r.denominator.value, currency)}</span>{r.denominator.method ? ` · ${r.denominator.method}` : ""}</dd></div>
          </dl>
          {r.note && <p className="mt-1 text-[11px] text-ink-400">{r.note}</p>}
        </li>
      ))}
    </ul>
  );
}

function useInvalidate(mic: string, ticker: string) {
  const qc = useQueryClient();
  return () => {
    for (const k of [["shariah", mic, ticker], ["analysis", mic, ticker], ["shariah-screener"], ["signals"], ["dashboard"]])
      qc.invalidateQueries({ queryKey: k });
  };
}

// ---------- editors ----------

function ActivitiesEditor({ base, initial, vocab, onSaved }: { base: string; initial: Activity[]; vocab: Vocabulary; onSaved: () => void }) {
  const [rows, setRows] = useState<Activity[]>(initial);
  useEffect(() => setRows(initial), [initial]);
  const save = useMutation({
    mutationFn: () => api(`${base}/activities`, { method: "PUT", body: JSON.stringify({ activities: rows }) }),
    onSuccess: onSaved,
  });
  const set = (i: number, patch: Partial<Activity>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const dirty = JSON.stringify(rows) !== JSON.stringify(initial);
  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed text-ink-400">
        Record what the company does, from its annual report or NGX profile. Mark the primary business. For any excluded activity that is
        not the main business, enter its share of revenue if the report states it; an unknown share makes the result QUESTIONABLE.
      </p>
      {rows.length === 0 && <p className="text-xs text-amber-300">No activities recorded. The business screen cannot pass until you add the primary business.</p>}
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-1 gap-2 rounded-lg border border-ink-800 p-3 sm:grid-cols-12">
          <label className="text-[11px] text-ink-400 sm:col-span-3">Activity
            <select className={inputCls} value={r.tag} onChange={(e) => set(i, { tag: e.target.value })}>
              <optgroup label="Permissible">{vocab.permissible.map((v) => <option key={v.tag} value={v.tag}>{v.label}</option>)}</optgroup>
              <optgroup label="On exclusion lists">{vocab.prohibited.map((v) => <option key={v.tag} value={v.tag}>{v.label}</option>)}</optgroup>
            </select>
          </label>
          <label className="text-[11px] text-ink-400 sm:col-span-3">Description
            <input className={inputCls} maxLength={160} value={r.label ?? ""} placeholder="e.g. Cement manufacturing" onChange={(e) => set(i, { label: e.target.value || null })} />
          </label>
          <label className="text-[11px] text-ink-400 sm:col-span-2">Revenue share %
            <input className={`${inputCls} num`} type="number" min={0} max={100} step="any" value={r.revenue_share === null ? "" : +(r.revenue_share * 100).toFixed(4)}
              onChange={(e) => set(i, { revenue_share: e.target.value === "" ? null : Math.min(100, Math.max(0, Number(e.target.value))) / 100 })} />
          </label>
          <label className="text-[11px] text-ink-400 sm:col-span-3">Source
            <input className={inputCls} maxLength={300} value={r.source ?? ""} placeholder="e.g. 2025 annual report, p. 12" onChange={(e) => set(i, { source: e.target.value || null })} />
          </label>
          <div className="flex items-end justify-between gap-2 sm:col-span-1 sm:flex-col sm:items-end">
            <label className="inline-flex items-center gap-1.5 text-[11px] text-ink-300">
              <input type="checkbox" className="accent-teal-500" checked={r.primary} onChange={() => set(i, { primary: !r.primary })} /> Primary
            </label>
            <button type="button" onClick={() => setRows(rows.filter((_, k) => k !== i))} className="p-1 text-ink-400 hover:text-red-400" aria-label="Remove activity"><Trash2 size={14} /></button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={btnSecondary} disabled={rows.length >= 20}
          onClick={() => setRows([...rows, { tag: "permissible", label: null, primary: rows.length === 0, revenue_share: null, source: null }])}>
          <Plus size={12} className="mr-1 inline" />Add activity
        </button>
        <button type="button" className={btnPrimary} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Save activities</button>
        {save.isError && <span role="alert" className="text-xs text-red-400">{(save.error as Error).message}</span>}
      </div>
    </div>
  );
}

const MONEY_GROUPS: { title: string; fields: [string, string, string][] }[] = [
  { title: "Income statement", fields: [
    ["revenue", "Revenue", "Turnover for the period"],
    ["interest_income", "Interest income", "Finance income from deposits and loans. Enter 0 if none"],
    ["non_permissible_income", "Other non-permissible income", "Excluding interest. Enter 0 if none"],
    ["net_income", "Net income", "Profit after tax (reference only)"],
  ] },
  { title: "Balance sheet", fields: [
    ["total_assets", "Total assets", ""],
    ["interest_bearing_debt", "Interest-bearing debt", "Loans, borrowings, bonds, overdrafts"],
    ["total_debt", "Total debt", "Used only if interest-bearing debt is blank"],
    ["cash", "Cash and equivalents", ""],
    ["interest_bearing_securities", "Interest-bearing securities", "Treasury bills, bonds, fixed deposits. Enter 0 if none"],
    ["receivables", "Receivables", "Trade and other receivables"],
    ["total_equity", "Total equity", "Reference only"],
    ["market_cap", "Market capitalisation", "Optional; otherwise last close × shares"],
  ] },
];
const UNITS: [number, string][] = [[1, "Units"], [1e3, "Thousands ('000)"], [1e6, "Millions"], [1e9, "Billions"]];

type FForm = Record<string, string | boolean>;
const emptyForm = (currency: string): FForm => ({
  period_end: "", period_type: "A", currency, reported_at: "", source_ref: "", is_estimate: false, note: "",
  shares_outstanding: "", dividend_per_share: "",
  ...Object.fromEntries(MONEY_GROUPS.flatMap((g) => g.fields.map(([k]) => [k, ""]))),
});

function FundamentalsEditor({ base, rows, currency, onSaved }: { base: string; rows: FundamentalsRow[]; currency: string; onSaved: () => void }) {
  const [f, setF] = useState<FForm>(emptyForm(currency));
  const [unit, setUnit] = useState(1);
  const moneyKeys = MONEY_GROUPS.flatMap((g) => g.fields.map(([k]) => k));
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        period_end: f.period_end, period_type: f.period_type, currency: f.currency, source_ref: f.source_ref,
        reported_at: f.reported_at || null, is_estimate: f.is_estimate, note: f.note || null,
        shares_outstanding: f.shares_outstanding === "" ? null : Number(f.shares_outstanding),
        dividend_per_share: f.dividend_per_share === "" ? null : Number(f.dividend_per_share),
      };
      for (const k of moneyKeys) body[k] = f[k] === "" ? null : Number(f[k]) * unit;
      return api(`${base}/fundamentals`, { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => { setF(emptyForm(currency)); setUnit(1); onSaved(); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`${base}/fundamentals/${id}`, { method: "DELETE" }), onSuccess: onSaved });
  const load = (r: FundamentalsRow) => {
    setUnit(1);
    setF({
      ...emptyForm(currency), period_end: r.period_end, period_type: r.period_type, currency: r.currency ?? currency,
      reported_at: r.reported_at ?? "", source_ref: r.source_ref ?? "", is_estimate: r.is_estimate, note: r.note ?? "",
      ...Object.fromEntries([...moneyKeys, "shares_outstanding", "dividend_per_share"].map((k) => [k, r[k] === null ? "" : String(r[k])])),
    });
  };
  const field = (k: string, label: string, hint = "") => (
    <label key={k} className="text-[11px] text-ink-400">{label}
      <input className={`${inputCls} num`} type="number" step="any" min={k === "net_income" || k === "total_equity" ? undefined : 0}
        value={String(f[k])} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
      {hint && <span className="mt-0.5 block text-[10px] text-ink-500">{hint}</span>}
    </label>
  );
  const ok = f.period_end && f.source_ref && String(f.source_ref).length >= 3 && /^[A-Z]{3}$/.test(String(f.currency));

  return (
    <div className="space-y-5">
      {rows.length === 0 ? (
        <EmptyState title="No fundamentals stored">
          The free EODHD plan has no fundamentals, so enter figures from the company's published financial statements
          (NGX issuer portal or the company's investor page). Each entry keeps its report reference.
        </EmptyState>
      ) : (
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-xs [&_td]:whitespace-nowrap">
            <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
              <tr>{["Period end", "Type", "Revenue", "Total assets", "Debt", "Cash", "Source", ""].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2">{fmtDate(r.period_end)}{r.is_estimate && <span className="ml-1 text-amber-300">(estimate)</span>}</td>
                  <td className="px-4 py-2">{r.period_type}</td>
                  <td className="num px-4 py-2">{fmtCompact(r.revenue as number | null)}</td>
                  <td className="num px-4 py-2">{fmtCompact(r.total_assets as number | null)}</td>
                  <td className="num px-4 py-2">{fmtCompact((r.interest_bearing_debt ?? r.total_debt) as number | null)}</td>
                  <td className="num px-4 py-2">{fmtCompact(r.cash as number | null)}</td>
                  <td className="max-w-[240px] truncate px-4 py-2 text-ink-400" title={r.source_ref ?? ""}>{r.source} · {r.source_ref}</td>
                  <td className="px-4 py-2 text-right">
                    <button className="mr-2 text-ink-300 hover:text-brand-500" onClick={() => load(r)}>Edit</button>
                    {r.source_code === "manual_fund" && (
                      <button className="text-ink-400 hover:text-red-400" onClick={() => { if (confirm(`Delete the ${r.period_type} figures for ${fmtDate(r.period_end)}?`)) del.mutate(r.id); }}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form className="space-y-4 rounded-lg border border-ink-800 p-4" onSubmit={(e) => { e.preventDefault(); if (ok) save.mutate(); }}>
        <p className="text-sm font-medium text-ink-100">Add or update a reporting period</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <label className="text-[11px] text-ink-400">Period end *<input className={inputCls} type="date" required value={String(f.period_end)} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></label>
          <label className="text-[11px] text-ink-400">Period type
            <select className={inputCls} value={String(f.period_type)} onChange={(e) => setF({ ...f, period_type: e.target.value })}>
              <option value="A">Annual</option><option value="H">Half-year</option><option value="Q">Quarter</option><option value="TTM">Trailing 12 months</option>
            </select>
          </label>
          <label className="text-[11px] text-ink-400">Published on<input className={inputCls} type="date" value={String(f.reported_at)} onChange={(e) => setF({ ...f, reported_at: e.target.value })} /></label>
          <label className="text-[11px] text-ink-400">Currency<input className={inputCls} maxLength={3} value={String(f.currency)} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></label>
          <label className="text-[11px] text-ink-400">Amounts are in
            <select className={inputCls} value={unit} onChange={(e) => setUnit(Number(e.target.value))}>
              {UNITS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="inline-flex items-end gap-1.5 pb-2 text-[11px] text-ink-300">
            <input type="checkbox" className="accent-teal-500" checked={Boolean(f.is_estimate)} onChange={() => setF({ ...f, is_estimate: !f.is_estimate })} /> Estimate, not reported
          </label>
        </div>
        <label className="block text-[11px] text-ink-400">Source reference * (report name and page, or https link)
          <input className={inputCls} required minLength={3} maxLength={500} value={String(f.source_ref)} placeholder="e.g. Dangote Cement H1 2026 unaudited results, p. 3"
            onChange={(e) => setF({ ...f, source_ref: e.target.value })} />
        </label>
        {MONEY_GROUPS.map((g) => (
          <fieldset key={g.title}>
            <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">{g.title}</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{g.fields.map(([k, l, h]) => field(k, l, h))}</div>
          </fieldset>
        ))}
        <fieldset>
          <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Per share (always in full units)</legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {field("shares_outstanding", "Shares outstanding", "Full count, not thousands")}
            {field("dividend_per_share", "Dividend per share", "For purification")}
          </div>
        </fieldset>
        <label className="block text-[11px] text-ink-400">Note<input className={inputCls} maxLength={1000} value={String(f.note)} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
        <p className="text-[11px] text-ink-500">Blank means unknown and is never treated as zero. A period with the same end date and type replaces the earlier entry.</p>
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className={btnPrimary} disabled={!ok || save.isPending}>Save figures</button>
          <button type="button" className={btnSecondary} onClick={() => { setF(emptyForm(currency)); setUnit(1); }}>Clear form</button>
          {save.isError && <span role="alert" className="text-xs text-red-400">{(save.error as Error).message}</span>}
          {del.isError && <span role="alert" className="text-xs text-red-400">{(del.error as Error).message}</span>}
        </div>
      </form>
    </div>
  );
}

function ReviewEditor({ base, data, onSaved }: { base: string; data: StockShariah; onSaved: () => void }) {
  const [note, setNote] = useState(data.review_note ?? "");
  const [ext, setExt] = useState<ExternalOpinion[]>(data.external);
  useEffect(() => { setNote(data.review_note ?? ""); setExt(data.external); }, [data.review_note, data.external]);
  const review = useMutation({
    mutationFn: (n: string | null) => api(`${base}/shariah-review`, { method: "PUT", body: JSON.stringify({ note: n }) }), onSuccess: onSaved,
  });
  const external = useMutation({
    mutationFn: () => api(`${base}/shariah-external`, { method: "PUT", body: JSON.stringify({ items: ext.map((e) => ({ ...e, url: e.url || null, note: e.note || null })) }) }),
    onSuccess: onSaved,
  });
  const set = (i: number, patch: Partial<ExternalOpinion>) => setExt(ext.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="space-y-2">
        <p className="text-sm font-medium text-ink-100">Manual review flag</p>
        <p className="text-xs text-ink-400">While a note is set the status shows UNDER REVIEW, unless a test fails outright.</p>
        <textarea className={`${inputCls} h-24`} maxLength={1000} value={note} placeholder="e.g. Awaiting audited 2026 accounts" onChange={(e) => setNote(e.target.value)} />
        <div className="flex gap-2">
          <button className={btnPrimary} disabled={!note.trim() || review.isPending} onClick={() => review.mutate(note)}>Flag for review</button>
          <button className={btnSecondary} disabled={!data.review_note || review.isPending} onClick={() => review.mutate(null)}>Clear flag</button>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium text-ink-100">External screens</p>
        <p className="text-xs text-ink-400">
          Record what another screener says, for example inclusion in the NGX Lotus Islamic Index, with the date you checked.
          If a recorded screen says NON-COMPLIANT while every test here passes, the result becomes QUESTIONABLE.
        </p>
        {ext.map((e, i) => (
          <div key={i} className="grid grid-cols-2 gap-2 rounded-lg border border-ink-800 p-2">
            <input className={inputCls} placeholder="Source" maxLength={160} value={e.source} onChange={(x) => set(i, { source: x.target.value })} aria-label="Source" />
            <select className={inputCls} value={e.status} onChange={(x) => set(i, { status: x.target.value as ExternalOpinion["status"] })} aria-label="Status">
              <option value="COMPLIANT">Compliant</option><option value="NON_COMPLIANT">Non-compliant</option><option value="QUESTIONABLE">Questionable</option>
            </select>
            <input className={inputCls} type="date" value={e.as_of} onChange={(x) => set(i, { as_of: x.target.value })} aria-label="Checked on" />
            <input className={inputCls} placeholder="https://…" maxLength={500} value={e.url ?? ""} onChange={(x) => set(i, { url: x.target.value })} aria-label="Link" />
            <input className={`${inputCls} col-span-2`} placeholder="Note" maxLength={500} value={e.note ?? ""} onChange={(x) => set(i, { note: x.target.value })} aria-label="Note" />
            <button className="col-span-2 justify-self-end text-[11px] text-ink-400 hover:text-red-400" onClick={() => setExt(ext.filter((_, k) => k !== i))}>Remove</button>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <button className={btnSecondary} disabled={ext.length >= 10}
            onClick={() => setExt([...ext, { source: "", status: "COMPLIANT", as_of: new Date().toISOString().slice(0, 10), url: "", note: "" }])}>
            <Plus size={12} className="mr-1 inline" />Add screen
          </button>
          <button className={btnPrimary} disabled={external.isPending || JSON.stringify(ext) === JSON.stringify(data.external) || ext.some((e) => e.source.length < 2 || !e.as_of)}
            onClick={() => external.mutate()}>Save external screens</button>
          {(external.isError || review.isError) && <span role="alert" className="text-xs text-red-400">{((external.error ?? review.error) as Error).message}</span>}
        </div>
      </div>
    </div>
  );
}

// ---------- panel ----------

const TABS = ["Business activities", "Fundamentals", "Reviews and external screens", "History"] as const;

export default function ShariahPanel({ mic, ticker, currency }: { mic: string; ticker: string; currency: string | null }) {
  const base = `/api/stocks/${mic}/${encodeURIComponent(ticker)}`;
  const [mid, setMid] = useState<number | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Business activities");
  const q = useQuery({
    queryKey: ["shariah", mic, ticker, mid],
    queryFn: () => api<StockShariah>(`${base}/shariah${mid ? `?methodology_id=${mid}` : ""}`),
  });
  const vocab = useQuery({ queryKey: ["shariah-vocab"], queryFn: () => api<Vocabulary>("/api/shariah/vocabulary"), staleTime: Infinity });
  const invalidate = useInvalidate(mic, ticker);
  const activities = useMemo(() => q.data?.activities ?? [], [q.data]);

  if (q.isLoading) return <p className="text-sm text-ink-400">Screening…</p>;
  if (q.isError || !q.data) return <p role="alert" className="text-sm text-red-400">Shariah screen failed: {(q.error as Error)?.message}</p>;
  const d = q.data;
  const r = d.result;
  const cur = d.currency ?? currency;
  const status = r.not_screened ? "NOT_SCREENED" : r.status;

  return (
    <section className="space-y-6" aria-labelledby="shariah-h">
      <h2 id="shariah-h" className="text-lg font-semibold">Shariah screening</h2>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={<span className="flex items-center gap-2">Result <ShariahBadge status={status} /></span>}
          action={
            <label className="text-[11px] text-ink-400">
              <span className="sr-only">Methodology</span>
              <select className="max-w-[11rem] truncate rounded-md border border-ink-700 bg-ink-950 px-2 py-1 text-xs text-ink-100 sm:max-w-none" value={mid ?? r.methodology.id}
                onChange={(e) => setMid(Number(e.target.value))}>
                {d.methodologies.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          }>
          <p className="text-sm text-ink-300">{r.not_screened ? "Nothing has been entered for this stock yet, so no compliance status is implied." : r.summary}</p>
          {r.reasons.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-ink-300">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}
          {r.warnings.length > 0 && (
            <ul className="mt-3 space-y-1">{r.warnings.map((w) => (
              <li key={w} className="flex gap-1.5 text-xs text-amber-300"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{w}</li>))}
            </ul>
          )}
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
            <div><dt className="text-ink-500">Methodology</dt><dd className="text-ink-100">{r.methodology.name}</dd></div>
            <div><dt className="text-ink-500">Denominator</dt><dd className="text-ink-100">{r.methodology.denominator_label}</dd></div>
            <div><dt className="text-ink-500">Fundamentals</dt><dd className="text-ink-100">{r.data ? `${PERIOD[r.data.period_type] ?? r.data.period_type} to ${fmtDate(r.data.period_end)}` : "None stored"}</dd></div>
            <div><dt className="text-ink-500">Data age</dt>
              <dd className={r.data && !r.data.fresh ? "text-amber-300" : "text-ink-100"}>{r.data ? `${r.data.age_days} days (limit ${r.data.max_age_days})` : "n/a"}</dd></div>
          </dl>
          {r.data && <p className="mt-2 text-[11px] text-ink-500">Source: {r.data.source} · {r.data.source_ref ?? "no reference"}{r.data.reported_at ? ` · published ${fmtDate(r.data.reported_at)}` : ""}</p>}
          {r.computed_at && <p className="mt-1 text-[11px] text-ink-500">Screen recorded {fmtDateTime(r.computed_at)}.</p>}
          <p className="mt-3 text-[11px] leading-relaxed text-ink-500">{d.disclaimer}</p>
        </Card>

        <Card title="Dividend purification">
          {r.purification ? (
            <div className="space-y-2 text-sm">
              <p className="num text-2xl font-semibold">{fmtMoney(r.purification.per_share, r.purification.currency ?? cur)}<span className="text-xs font-normal text-ink-400"> per share</span></p>
              <p className="text-xs text-ink-300">{pct(r.purification.ratio, 2)} of a {fmtMoney(r.purification.dividend_per_share, r.purification.currency ?? cur)} dividend.</p>
              <p className="text-[11px] leading-relaxed text-ink-500">{r.purification.note}</p>
            </div>
          ) : (
            <p className="text-xs text-ink-400">Needs dividend per share, revenue, interest income and other non-permissible income for the same period.</p>
          )}
        </Card>

        <Card className="lg:col-span-2" title="Why? Financial ratio tests"><Ratios ratios={r.ratios} currency={cur} /></Card>

        <Card title="Why? Business activities">
          <div className="mb-2 flex items-center gap-2"><ResultChip r={r.business.result} /><span className="text-xs text-ink-300">{r.business.message}</span></div>
          <ul className="divide-y divide-ink-800 text-xs">
            {r.business.items.map((a, i) => (
              <li key={i} className="py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-ink-100">{a.label}{a.primary && <span className="ml-1 text-[10px] uppercase text-brand-500">primary</span>}</span>
                  <ResultChip r={a.result} />
                </div>
                <p className="mt-0.5 text-ink-400">{a.note}{a.revenue_share !== null ? ` Revenue share ${pct(a.revenue_share)}.` : ""}</p>
                {a.source && <p className="text-[11px] text-ink-500">Source: {a.source}</p>}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Screening inputs">
        <div className="mb-4 flex flex-wrap gap-1" role="tablist" aria-label="Screening inputs">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className={`rounded px-2.5 py-1 text-xs font-medium ${tab === t ? "bg-brand-600/20 text-brand-500" : "text-ink-400 hover:text-ink-100"}`}>{t}</button>
          ))}
        </div>
        {tab === "Business activities" && vocab.data && <ActivitiesEditor base={base} initial={activities} vocab={vocab.data} onSaved={invalidate} />}
        {tab === "Fundamentals" && <FundamentalsEditor base={base} rows={d.fundamentals} currency={cur ?? "NGN"} onSaved={invalidate} />}
        {tab === "Reviews and external screens" && <ReviewEditor base={base} data={d} onSaved={invalidate} />}
        {tab === "History" && (d.history.length === 0 ? <p className="text-xs text-ink-400">No screen recorded yet.</p> : (
          <ul className="divide-y divide-ink-800 text-xs">
            {d.history.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="text-ink-300">{fmtDateTime(h.computed_at)} · {h.methodology}{h.data_as_of ? ` · data to ${fmtDate(h.data_as_of)}` : ""}</span>
                <ShariahBadge status={h.status} />
              </li>
            ))}
          </ul>
        ))}
      </Card>
    </section>
  );
}
