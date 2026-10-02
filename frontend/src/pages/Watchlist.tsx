import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtMoney, fmtPct } from "../lib/format";
import type { StockRef, WatchlistsResponse } from "../lib/types";
import { DataStatusBadge, ShariahBadge, SignalBadge } from "../components/badges";
import { btnPrimary, btnSecondary, inputCls } from "../components/ShariahPanel";
import StockPicker from "../components/StockPicker";
import { Card, EmptyState } from "../components/ui";

export default function Watchlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["watchlists"], queryFn: () => api<WatchlistsResponse>("/api/watchlists") });
  const [sel, setSel] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [pick, setPick] = useState<StockRef | null>(null);
  const [note, setNote] = useState("");
  const done = () => { qc.invalidateQueries({ queryKey: ["watchlists"] }); qc.invalidateQueries({ queryKey: ["membership"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); };
  const create = useMutation({
    mutationFn: (name: string) => api<{ id: number }>("/api/watchlists", { method: "POST", body: JSON.stringify({ name }) }),
    onSuccess: (w) => { setNewName(""); setSel(w.id); done(); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/watchlists/${id}`, { method: "DELETE" }), onSuccess: () => { setSel(null); done(); } });
  const add = useMutation({
    mutationFn: (wid: number) => api(`/api/watchlists/${wid}/items`, { method: "POST", body: JSON.stringify({ exchange: pick!.exchange, ticker: pick!.ticker, note: note || null }) }),
    onSuccess: () => { setPick(null); setNote(""); done(); },
  });
  const remove = useMutation({
    mutationFn: ({ wid, ex, t }: { wid: number; ex: string; t: string }) => api(`/api/watchlists/${wid}/items/${ex}/${encodeURIComponent(t)}`, { method: "DELETE" }),
    onSuccess: done,
  });

  const lists = q.data?.watchlists ?? [];
  const w = lists.find((x) => x.id === sel) ?? lists[0];
  const err = create.error ?? del.error ?? add.error ?? remove.error;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Watchlist</h1>
        <p className="text-xs text-ink-400">Stored prices only: opening this page uses none of your EODHD calls. Open a stock to refresh it.</p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Watchlists">
          {lists.map((x) => (
            <button key={x.id} role="tab" aria-selected={w?.id === x.id} onClick={() => setSel(x.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${w?.id === x.id ? "bg-ink-800 text-ink-100 ring-1 ring-ink-700" : "text-ink-400 hover:text-ink-100"}`}>
              {x.name} <span className="num text-ink-500">{x.items.length}</span>
            </button>
          ))}
        </div>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) create.mutate(newName.trim()); }}>
          <label className="text-[11px] text-ink-400">New watchlist
            <input className={`${inputCls} w-44`} maxLength={80} value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. NGX banks" />
          </label>
          <button className={btnSecondary} disabled={!newName.trim() || create.isPending}>Create</button>
        </form>
      </div>
      {err && <p role="alert" className="text-xs text-red-400">{(err as Error).message}</p>}

      {q.isLoading ? <p className="text-sm text-ink-400">Loading…</p> : !w ? (
        <EmptyState title="No watchlist yet">Create one above, or use "Watch" on any stock page.</EmptyState>
      ) : (
        <Card title={w.name} action={
          <button className="text-[11px] text-ink-400 hover:text-red-400" onClick={() => { if (confirm(`Delete the watchlist "${w.name}"?`)) del.mutate(w.id); }}>Delete list</button>
        }>
          <form className="mb-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); if (pick) add.mutate(w.id); }}>
            <StockPicker value={pick} onChange={setPick} label="Add a stock" />
            <label className="text-[11px] text-ink-400 sm:col-span-2">Note
              <input className={inputCls} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you are watching it" />
            </label>
            <button className={btnPrimary} disabled={!pick || add.isPending}>Add to {w.name}</button>
          </form>
          {w.items.length === 0 ? <EmptyState title="This watchlist is empty">Add stocks above or from a stock page.</EmptyState> : (
            <div className="-mx-4 -mb-4 overflow-x-auto">
              <table className="w-full min-w-[960px] text-sm [&_td]:whitespace-nowrap">
                <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                  <tr>{["Stock", "Last close", "Change", "Data", "Shariah", "Signal", "Score", "Note", "Added", ""].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-ink-800">
                  {w.items.map((r) => (
                    <tr key={`${r.exchange}-${r.ticker}`} className="hover:bg-ink-850">
                      <td className="px-4 py-2.5">
                        <Link to={`/stocks/${r.exchange}/${encodeURIComponent(r.ticker)}`} className="font-medium hover:text-brand-500">{r.ticker}</Link>
                        <p className="max-w-[180px] truncate text-[11px] text-ink-400">{r.name}</p>
                      </td>
                      <td className="num px-4 py-2.5">{fmtMoney(r.quote.price, r.currency)}</td>
                      <td className={`num px-4 py-2.5 ${r.quote.change_pct === null ? "text-ink-400" : r.quote.change_pct >= 0 ? "text-up" : "text-down"}`}>{fmtPct(r.quote.change_pct)}</td>
                      <td className="px-4 py-2.5"><DataStatusBadge status={r.quote.status} title={r.quote.note ?? undefined} /><p className="text-[10px] text-ink-500">{fmtDate(r.quote.as_of)}</p></td>
                      <td className="px-4 py-2.5"><ShariahBadge status={r.shariah} /></td>
                      <td className="px-4 py-2.5">{r.signal ? <SignalBadge type={r.signal.type} /> : <span className="text-[11px] text-ink-500">Not computed</span>}</td>
                      <td className="num px-4 py-2.5">{r.signal?.score == null ? "n/a" : r.signal.score.toFixed(0)}</td>
                      <td className="max-w-[200px] truncate px-4 py-2.5 text-xs text-ink-400" title={r.note ?? ""}>{r.note}</td>
                      <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDate(r.added_at)}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button className="p-1 text-ink-400 hover:text-red-400" aria-label={`Remove ${r.ticker}`} onClick={() => remove.mutate({ wid: w.id, ex: r.exchange, t: r.ticker })}><Trash2 size={14} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      <p className="text-[11px] text-ink-500">Shariah status uses {q.data?.methodology ?? "your default methodology"}. The signal is the latest one stored for each stock.</p>
    </div>
  );
}
