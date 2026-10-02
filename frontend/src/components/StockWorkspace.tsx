import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Briefcase, Star } from "lucide-react";
import { api } from "../lib/api";
import type { PortfoliosResponse } from "../lib/types";
import AlertForm from "./AlertForm";
import PositionForm from "./PositionForm";
import { btnSecondary } from "./ShariahPanel";
import { Card } from "./ui";

interface Membership { watchlists: { id: number; name: string; contains: boolean }[]; open_positions: number; alerts: number }

export default function StockWorkspace({ mic, ticker, name }: { mic: string; ticker: string; name: string }) {
  const qc = useQueryClient();
  const base = `/api/stocks/${mic}/${encodeURIComponent(ticker)}`;
  const m = useQuery({ queryKey: ["membership", mic, ticker], queryFn: () => api<Membership>(`${base}/membership`) });
  const [panel, setPanel] = useState<"" | "position" | "alert">("");
  const ports = useQuery({ queryKey: ["portfolios"], queryFn: () => api<PortfoliosResponse>("/api/portfolios"), enabled: panel === "position" });
  const done = () => { for (const k of ["membership", "watchlists", "dashboard"]) qc.invalidateQueries({ queryKey: [k] }); };
  const toggle = useMutation({
    mutationFn: async (w: { id: number; contains: boolean }) => w.contains
      ? api(`/api/watchlists/${w.id}/items/${mic}/${encodeURIComponent(ticker)}`, { method: "DELETE" })
      : api(`/api/watchlists/${w.id}/items`, { method: "POST", body: JSON.stringify({ exchange: mic, ticker }) }),
    onSuccess: done,
  });
  const quick = useMutation({
    mutationFn: async () => {
      const w = await api<{ id: number }>("/api/watchlists", { method: "POST", body: JSON.stringify({ name: "My watchlist" }) });
      return api(`/api/watchlists/${w.id}/items`, { method: "POST", body: JSON.stringify({ exchange: mic, ticker }) });
    },
    onSuccess: done,
  });
  const newPortfolio = useMutation({
    mutationFn: () => api("/api/portfolios", { method: "POST", body: JSON.stringify({ name: "My portfolio", base_currency: "NGN" }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolios"] }),
  });
  const d = m.data;
  const err = toggle.error ?? quick.error ?? newPortfolio.error;
  return (
    <Card title="Your watchlists, holdings and alerts">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Star size={14} className="text-ink-400" aria-hidden />
        {d && d.watchlists.length === 0 && <button className={btnSecondary} onClick={() => quick.mutate()} disabled={quick.isPending}>Watch (creates "My watchlist")</button>}
        {d?.watchlists.map((w) => (
          <label key={w.id} className="inline-flex items-center gap-1.5 rounded-md bg-ink-800 px-2 py-1 text-ink-300 ring-1 ring-ink-700">
            <input type="checkbox" className="accent-teal-500" checked={w.contains} onChange={() => toggle.mutate(w)} disabled={toggle.isPending} /> {w.name}
          </label>
        ))}
        <span className="mx-2 h-4 w-px bg-ink-700" aria-hidden />
        <Briefcase size={14} className="text-ink-400" aria-hidden />
        <span className="text-ink-300">{d?.open_positions ? <Link to="/portfolio" className="hover:text-brand-500">{d.open_positions} open position(s)</Link> : "Not held"}</span>
        <button className={btnSecondary} onClick={() => setPanel(panel === "position" ? "" : "position")}>Add position</button>
        <span className="mx-2 h-4 w-px bg-ink-700" aria-hidden />
        <Bell size={14} className="text-ink-400" aria-hidden />
        <span className="text-ink-300">{d?.alerts ? <Link to="/alerts" className="hover:text-brand-500">{d.alerts} alert(s)</Link> : "No alerts"}</span>
        <button className={btnSecondary} onClick={() => setPanel(panel === "alert" ? "" : "alert")}>New alert</button>
      </div>
      {err && <p role="alert" className="mt-2 text-xs text-red-400">{(err as Error).message}</p>}
      {panel === "position" && (
        <div className="mt-4 border-t border-ink-800 pt-4">
          {ports.data && ports.data.portfolios.length === 0 ? (
            <button className={btnSecondary} onClick={() => newPortfolio.mutate()} disabled={newPortfolio.isPending}>Create "My portfolio" (NGN) first</button>
          ) : ports.data ? (
            <PositionForm portfolios={ports.data.portfolios.map((p) => ({ id: p.id, name: p.name }))} stock={{ exchange: mic, ticker, name }} onDone={() => setPanel("")} />
          ) : <p className="text-xs text-ink-400">Loading…</p>}
        </div>
      )}
      {panel === "alert" && <div className="mt-4 border-t border-ink-800 pt-4"><AlertForm stock={{ exchange: mic, ticker, name }} /></div>}
    </Card>
  );
}
