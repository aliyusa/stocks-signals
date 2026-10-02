import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { StockRef, StockRow } from "../lib/types";
import { inputCls } from "./ShariahPanel";

/** Picks a stock already in the local universe. Free: it never calls a data provider. */
export default function StockPicker({ value, onChange, label = "Stock" }: {
  value: StockRef | null; onChange: (s: StockRef | null) => void; label?: string;
}) {
  const [q, setQ] = useState(value ? value.ticker : "");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLLabelElement>(null);
  const term = q.trim();
  const res = useQuery({
    queryKey: ["picker", term],
    queryFn: () => api<{ results: StockRow[] }>(`/api/search?q=${encodeURIComponent(term)}`),
    enabled: term.length >= 1 && open,
  });
  useEffect(() => { if (value) setQ(value.ticker); }, [value]);
  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const rows = (res.data?.results ?? []).filter((r) => r.type !== "index").slice(0, 8);
  return (
    <label ref={box} className="relative block text-[11px] text-ink-400">{label}
      <input className={inputCls} value={q} placeholder="Ticker or name" autoComplete="off"
        onChange={(e) => { setQ(e.target.value); setOpen(true); onChange(null); }} onFocus={() => setOpen(true)} />
      {value && <span className="mt-0.5 block text-[10px] text-ink-500">{value.exchange} · {value.name ?? value.ticker}</span>}
      {open && term && (
        <ul className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-ink-700 bg-ink-900 text-xs shadow-lg">
          {rows.length === 0 && <li className="px-3 py-2 text-ink-400">{res.isLoading ? "Searching…" : "No match in the local universe. Use the top search to add it."}</li>}
          {rows.map((r) => (
            <li key={`${r.exchange}-${r.ticker}`}>
              <button type="button" className="flex w-full justify-between gap-2 px-3 py-2 text-left hover:bg-ink-800"
                onClick={() => { onChange({ exchange: r.exchange, ticker: r.ticker, name: r.name }); setQ(r.ticker); setOpen(false); }}>
                <span className="font-medium text-ink-100">{r.ticker}</span>
                <span className="truncate text-ink-400">{r.name} · {r.exchange}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}
