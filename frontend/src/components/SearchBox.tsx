import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CloudDownload, Search } from "lucide-react";
import { api } from "../lib/api";
import { fmtMoney, fmtPct } from "../lib/format";
import { useMarket } from "../lib/market";
import type { StockRow, Usage } from "../lib/types";
import { DataStatusBadge } from "./badges";

function useDebounced<T>(v: T, ms: number) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export default function SearchBox() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { market } = useMarket();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [remote, setRemote] = useState<{ results: StockRow[]; error: string | null; usage: Usage } | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const dq = useDebounced(q.trim(), 200);

  const local = useQuery({
    queryKey: ["search", dq, market],
    queryFn: () => api<{ results: StockRow[] }>(`/api/search?q=${encodeURIComponent(dq)}&market=${market}`),
    enabled: dq.length >= 1,
  });

  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  useEffect(() => setRemote(null), [dq]);

  async function searchProvider() {
    if (!dq) return;
    setBusy(true);
    try {
      setRemote(await api("/api/search/provider", { method: "POST", body: JSON.stringify({ q: dq, market }) }));
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["stocks"] });
    } catch (e) {
      setRemote({ results: [], error: (e as Error).message, usage: { source: "eodhd", day: "", used: 0, limit: 0, remaining: 0 } });
    } finally {
      setBusy(false);
    }
  }

  function go(s: StockRow) {
    setOpen(false);
    setQ("");
    nav(`/stocks/${s.exchange}/${encodeURIComponent(s.ticker)}`);
  }

  const rows = remote?.results.length ? remote.results : (local.data?.results ?? []);

  return (
    <div ref={box} className="relative w-full max-w-sm">
      <label className="flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-900 px-3 py-1.5 focus-within:border-brand-500">
        <Search size={14} className="text-ink-400" aria-hidden />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && rows[0]) go(rows[0]);
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Search ticker or company (e.g. DANGCEM, MSFT)"
          aria-label="Search stocks"
          maxLength={64}
          className="w-full bg-transparent text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none"
        />
      </label>
      {open && dq && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-ink-700 bg-ink-900 shadow-2xl sm:w-[28rem]">
          <ul className="max-h-80 divide-y divide-ink-800 overflow-y-auto">
            {rows.map((s) => (
              <li key={`${s.exchange}:${s.ticker}`}>
                <button onClick={() => go(s)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-ink-800">
                  <span className="min-w-0">
                    <span className="text-sm font-semibold">{s.ticker}</span>
                    <span className="ml-2 text-[11px] text-ink-500">{s.exchange}</span>
                    <span className="block truncate text-xs text-ink-400">{s.name}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="num block text-xs">{s.quote.price === null ? "Data unavailable" : fmtMoney(s.quote.price, s.currency)}</span>
                    {s.quote.change_pct !== null && (
                      <span className={`num text-[11px] ${s.quote.change_pct >= 0 ? "text-up" : "text-down"}`}>{fmtPct(s.quote.change_pct)}</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {!rows.length && !local.isLoading && (
            <p className="px-3 py-2 text-xs text-ink-400">Not in your local universe yet.</p>
          )}
          {remote?.error && <p role="alert" className="border-t border-ink-800 px-3 py-2 text-xs text-amber-300">{remote.error}</p>}
          {remote && !remote.error && remote.results.length === 0 && (
            <p className="border-t border-ink-800 px-3 py-2 text-xs leading-snug text-amber-300">
              EODHD search found no match. Its search index covers NGX poorly: load Nigerian stocks with{" "}
              <button className="underline" onClick={() => { setOpen(false); nav("/markets"); }}>Markets → Import NGX list</button>.
            </p>
          )}
          <div className="flex items-center justify-between gap-2 border-t border-ink-800 bg-ink-850 px-3 py-2">
            <span className="text-[11px] text-ink-500">
              {remote?.usage?.limit ? `EODHD calls today: ${remote.usage.used}/${remote.usage.limit}` : "Local results are free"}
            </span>
            <button onClick={searchProvider} disabled={busy} className="inline-flex items-center gap-1 rounded-md bg-ink-800 px-2 py-1 text-[11px] font-medium text-ink-100 ring-1 ring-ink-700 hover:bg-ink-700 disabled:opacity-60">
              <CloudDownload size={12} /> {busy ? "Searching…" : "Search EODHD (1 call)"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function QuoteStatus({ s }: { s: StockRow }) {
  return <DataStatusBadge status={s.quote.status} title={s.quote.note ?? undefined} />;
}
