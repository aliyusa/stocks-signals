import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import type { PortfolioData, PortfoliosResponse, PositionRow } from "../lib/types";
import { ShariahBadge, SignalBadge } from "../components/badges";
import PositionForm, { invalidateWorkspace } from "../components/PositionForm";
import { btnPrimary, btnSecondary, inputCls } from "../components/ShariahPanel";
import { Card, EmptyState, Stat } from "../components/ui";

const plCls = (v: number | null | undefined) => (v == null ? "text-ink-400" : v >= 0 ? "text-up" : "text-down");

function CloseForm({ pos, onDone }: { pos: PositionRow; onDone: () => void }) {
  const qc = useQueryClient();
  const [price, setPrice] = useState(pos.quote.price != null ? String(pos.quote.price) : "");
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const close = useMutation({
    mutationFn: () => api(`/api/positions/${pos.id}/close`, { method: "POST", body: JSON.stringify({ exit_price: Number(price), closed_at: day }) }),
    onSuccess: () => { invalidateWorkspace(qc); onDone(); },
  });
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(price) > 0) close.mutate(); }}>
      <label className="text-[11px] text-ink-400">Exit price<input className={`${inputCls} num w-32`} type="number" step="any" min={0} value={price} onChange={(e) => setPrice(e.target.value)} /></label>
      <label className="text-[11px] text-ink-400">Closed on<input className={`${inputCls} w-40`} type="date" value={day} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDay(e.target.value)} /></label>
      <button className={btnPrimary} disabled={!(Number(price) > 0) || close.isPending}>Record sale</button>
      <button type="button" className={btnSecondary} onClick={onDone}>Cancel</button>
      {close.isError && <span role="alert" className="text-xs text-red-400">{(close.error as Error).message}</span>}
    </form>
  );
}

function OpenTable({ p }: { p: PortfolioData }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<number | null>(null);
  const [closing, setClosing] = useState<number | null>(null);
  const del = useMutation({ mutationFn: (id: number) => api(`/api/positions/${id}`, { method: "DELETE" }), onSuccess: () => invalidateWorkspace(qc) });
  if (!p.open.length) return <EmptyState title="No open positions">Add what you hold below. Values use the latest stored close.</EmptyState>;
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="w-full min-w-[1100px] text-sm [&_td]:whitespace-nowrap">
        <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
          <tr>{["Stock", "Qty", "Avg entry", "Last close", "Value", "P/L", "Stop", "Target", "Shariah", "Signal", ""].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-ink-800">
          {p.open.map((r) => (
            <Fragment key={r.id}>
              <tr className="align-top hover:bg-ink-850">
                <td className="px-4 py-2.5">
                  <Link to={`/stocks/${r.exchange}/${encodeURIComponent(r.ticker)}`} className="font-medium hover:text-brand-500">{r.ticker}</Link>
                  <p className="max-w-[160px] truncate text-[11px] text-ink-400">{r.name}</p>
                </td>
                <td className="num px-4 py-2.5">{fmtNum(r.quantity, 0)}</td>
                <td className="num px-4 py-2.5">{fmtMoney(r.avg_entry, r.currency)}</td>
                <td className="num px-4 py-2.5">{fmtMoney(r.quote.price, r.currency)}<p className="text-[10px] text-ink-500">{fmtDate(r.quote.as_of)}</p></td>
                <td className="num px-4 py-2.5">{fmtMoney(r.value, r.currency)}</td>
                <td className={`num px-4 py-2.5 ${plCls(r.pl)}`}>{fmtMoney(r.pl, null)}<p className="text-[11px]">{fmtPct(r.pl_pct)}</p></td>
                <td className="num px-4 py-2.5">{r.stop == null ? <span className="text-amber-300">Not set</span> : fmtMoney(r.stop, null)}<p className="text-[10px] text-ink-500">{r.to_stop_pct == null ? "" : `${fmtPct(r.to_stop_pct)} away`}</p></td>
                <td className="num px-4 py-2.5">{r.target == null ? "n/a" : fmtMoney(r.target, null)}<p className="text-[10px] text-ink-500">{r.to_target_pct == null ? "" : `${fmtPct(r.to_target_pct)} away`}</p></td>
                <td className="px-4 py-2.5"><ShariahBadge status={r.shariah} /></td>
                <td className="px-4 py-2.5">
                  {r.signal ? <SignalBadge type={r.signal.type} /> : <span className="text-[11px] text-ink-500">Needs 30 bars</span>}
                  {r.signal?.triggered.map((x) => <p key={x.code} className="mt-0.5 max-w-[220px] whitespace-normal text-[10px] text-amber-300">{x.label}</p>)}
                </td>
                <td className="px-4 py-2.5 text-right text-[11px]">
                  <button className="mr-2 text-ink-300 hover:text-brand-500" onClick={() => { setEdit(edit === r.id ? null : r.id); setClosing(null); }}>Edit</button>
                  <button className="mr-2 text-ink-300 hover:text-brand-500" onClick={() => { setClosing(closing === r.id ? null : r.id); setEdit(null); }}>Close</button>
                  <button className="text-ink-400 hover:text-red-400" onClick={() => { if (confirm(`Delete the ${r.ticker} position? Use Close instead to keep it in the record.`)) del.mutate(r.id); }}>Delete</button>
                </td>
              </tr>
              {(edit === r.id || closing === r.id) && (
                <tr><td colSpan={11} className="bg-ink-950/40 px-4 py-3">
                  {edit === r.id ? <PositionForm portfolios={[{ id: p.id, name: p.name }]} initial={r} onDone={() => setEdit(null)} /> : <CloseForm pos={r} onDone={() => setClosing(null)} />}
                </td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Exposure({ p }: { p: PortfolioData }) {
  const curs = Object.keys(p.exposure);
  if (!curs.length) return <p className="text-xs text-ink-400">No priced holdings.</p>;
  return (
    <div className="space-y-4">
      {curs.map((cur) => (["sector", "market"] as const).map((k) => (
        <div key={`${cur}-${k}`}>
          <p className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">By {k} · {cur}</p>
          <ul className="space-y-1.5">
            {p.exposure[cur][k].map((x) => (
              <li key={x.name} className="text-xs">
                <div className="flex justify-between gap-2"><span className="text-ink-300">{x.name}</span><span className="num text-ink-100">{fmtNum(x.share * 100, 1)}%</span></div>
                <div className="mt-0.5 h-1.5 rounded bg-ink-800" aria-hidden><div className="h-full rounded bg-brand-500" style={{ width: `${x.share * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        </div>
      )))}
    </div>
  );
}

export default function Portfolio() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portfolios"], queryFn: () => api<PortfoliosResponse>("/api/portfolios") });
  const [sel, setSel] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [cur, setCur] = useState("NGN");
  const create = useMutation({
    mutationFn: () => api<{ id: number }>("/api/portfolios", { method: "POST", body: JSON.stringify({ name, base_currency: cur }) }),
    onSuccess: (x) => { setName(""); setSel(x.id); qc.invalidateQueries({ queryKey: ["portfolios"] }); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/portfolios/${id}`, { method: "DELETE" }), onSuccess: () => { setSel(null); invalidateWorkspace(qc); } });
  const ps = q.data?.portfolios ?? [];
  const p = ps.find((x) => x.id === sel) ?? ps[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Portfolio</h1>
        <p className="text-xs text-ink-400">{q.data?.note ?? "Manually entered holdings."} Held stocks are rated HOLD or SELL / EXIT with the reason shown.</p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Portfolios">
          {ps.map((x) => (
            <button key={x.id} role="tab" aria-selected={p?.id === x.id} onClick={() => setSel(x.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${p?.id === x.id ? "bg-ink-800 text-ink-100 ring-1 ring-ink-700" : "text-ink-400 hover:text-ink-100"}`}>{x.name}</button>
          ))}
        </div>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
          <label className="text-[11px] text-ink-400">New portfolio<input className={`${inputCls} w-44`} maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Long-term NGX" /></label>
          <label className="text-[11px] text-ink-400">Base currency<input className={`${inputCls} w-20`} maxLength={3} value={cur} onChange={(e) => setCur(e.target.value.toUpperCase())} /></label>
          <button className={btnSecondary} disabled={!name.trim() || !/^[A-Z]{3}$/.test(cur) || create.isPending}>Create</button>
        </form>
      </div>
      {(create.error || del.error) && <p role="alert" className="text-xs text-red-400">{((create.error ?? del.error) as Error).message}</p>}

      {q.isLoading ? <p className="text-sm text-ink-400">Loading…</p> : q.isError ? <p role="alert" className="text-sm text-red-400">{(q.error as Error).message}</p> : !p ? (
        <EmptyState title="No portfolio yet">Create one above, then record the positions you hold.</EmptyState>
      ) : (
        <>
          {p.warnings.length > 0 && (
            <ul className="space-y-1">{p.warnings.map((w) => <li key={w} className="flex gap-1.5 text-xs text-amber-300"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{w}</li>)}</ul>
          )}
          {Object.entries(p.totals).map(([c, t]) => (
            <div key={c} className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label={`Value · ${c}`} value={fmtMoney(t.value, c)} hint={`${t.priced} priced${t.unpriced ? `, ${t.unpriced} without price` : ""}`} />
              <Stat label="Cost" value={fmtMoney(t.cost, c)} />
              <Stat label="Unrealised P/L" value={<span className={plCls(t.unrealised)}>{fmtMoney(t.unrealised, c)}</span>} hint={t.cost ? fmtPct((t.unrealised / t.cost) * 100) : undefined} />
              <Stat label="Realised P/L" value={<span className={plCls(t.realised)}>{fmtMoney(t.realised, c)}</span>} hint="From closed positions" />
            </div>
          ))}
          <div className="grid grid-cols-1 gap-6 2xl:grid-cols-4">
            <Card title={`${p.name} · open positions`} className="2xl:col-span-3"
              action={<button className="text-[11px] text-ink-400 hover:text-red-400" onClick={() => { if (confirm(`Delete "${p.name}" and all its positions?`)) del.mutate(p.id); }}>Delete portfolio</button>}>
              <OpenTable p={p} />
            </Card>
            <Card title="Exposure"><Exposure p={p} /></Card>
          </div>
          <Card title="Add a position"><PositionForm portfolios={[{ id: p.id, name: p.name }]} /></Card>
          {p.closed.length > 0 && (
            <Card title="Closed positions">
              <div className="-mx-4 -my-4 overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm [&_td]:whitespace-nowrap">
                  <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                    <tr>{["Stock", "Qty", "Entry", "Exit", "Opened", "Closed", "Realised P/L"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-ink-800">
                    {p.closed.map((r) => (
                      <tr key={r.id}>
                        <td className="px-4 py-2.5 font-medium">{r.ticker}</td>
                        <td className="num px-4 py-2.5">{fmtNum(r.quantity, 0)}</td>
                        <td className="num px-4 py-2.5">{fmtMoney(r.avg_entry, r.currency)}</td>
                        <td className="num px-4 py-2.5">{fmtMoney(r.exit_price, r.currency)}</td>
                        <td className="px-4 py-2.5 text-xs">{fmtDate(r.opened_at)}</td>
                        <td className="px-4 py-2.5 text-xs">{fmtDate(r.closed_at)}</td>
                        <td className={`num px-4 py-2.5 ${plCls(r.pl)}`}>{fmtMoney(r.pl, r.currency)} ({fmtPct(r.pl_pct)})</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
      <p className="text-[11px] text-ink-500">Shariah status uses {q.data?.methodology ?? "your default methodology"}. Exits are explained on each stock page under the signal.</p>
    </div>
  );
}
