import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { PositionRow, StockRef } from "../lib/types";
import { btnPrimary, btnSecondary, inputCls } from "./ShariahPanel";
import StockPicker from "./StockPicker";

export function invalidateWorkspace(qc: ReturnType<typeof useQueryClient>) {
  for (const k of ["portfolios", "analysis", "signals", "membership", "dashboard", "watchlists"]) qc.invalidateQueries({ queryKey: [k] });
}

const today = () => new Date().toISOString().slice(0, 10);

/** Add a position (portfolios + optional fixed stock) or edit one (initial). */
export default function PositionForm({ portfolios, stock, initial, onDone }: {
  portfolios: { id: number; name: string }[]; stock?: StockRef; initial?: PositionRow; onDone?: () => void;
}) {
  const qc = useQueryClient();
  const [pid, setPid] = useState(portfolios[0]?.id ?? 0);
  const [pick, setPick] = useState<StockRef | null>(stock ?? null);
  const [f, setF] = useState({
    quantity: initial ? String(initial.quantity) : "", avg_entry: initial ? String(initial.avg_entry) : "",
    stop: initial?.stop != null ? String(initial.stop) : "", target: initial?.target != null ? String(initial.target) : "",
    opened_at: initial?.opened_at ?? today(), note: initial?.note ?? "",
  });
  const num = (v: string) => (v === "" ? null : Number(v));
  const save = useMutation({
    mutationFn: () => {
      const body = { quantity: Number(f.quantity), avg_entry: Number(f.avg_entry), stop: num(f.stop), target: num(f.target),
        opened_at: f.opened_at || null, note: f.note || null };
      return initial
        ? api(`/api/positions/${initial.id}`, { method: "PUT", body: JSON.stringify(body) })
        : api(`/api/portfolios/${pid}/positions`, { method: "POST", body: JSON.stringify({ ...body, exchange: pick!.exchange, ticker: pick!.ticker }) });
    },
    onSuccess: () => { invalidateWorkspace(qc); onDone?.(); },
  });
  const ok = (initial || (pick && pid)) && Number(f.quantity) > 0 && Number(f.avg_entry) > 0
    && !(f.stop && f.target && Number(f.stop) >= Number(f.target));
  const field = (k: keyof typeof f, label: string, type = "number") => (
    <label className="text-[11px] text-ink-400">{label}
      <input className={`${inputCls} ${type === "number" ? "num" : ""}`} type={type} step="any" min={type === "number" ? 0 : undefined}
        max={type === "date" ? today() : undefined} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </label>
  );
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (ok) save.mutate(); }}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {!initial && portfolios.length > 1 && (
          <label className="text-[11px] text-ink-400">Portfolio
            <select className={inputCls} value={pid} onChange={(e) => setPid(Number(e.target.value))}>
              {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        )}
        {!initial && !stock && <StockPicker value={pick} onChange={setPick} />}
        {field("quantity", "Quantity (shares)")}
        {field("avg_entry", "Average entry price")}
        {field("stop", "Stop (optional)")}
        {field("target", "Target (optional)")}
        {field("opened_at", "Opened on", "date")}
        <label className="col-span-2 text-[11px] text-ink-400">Note
          <input className={inputCls} maxLength={500} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        </label>
      </div>
      {f.stop && f.target && Number(f.stop) >= Number(f.target) && <p className="text-xs text-amber-300">The stop must be below the target.</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={btnPrimary} disabled={!ok || save.isPending}>{initial ? "Save changes" : "Add position"}</button>
        {onDone && <button type="button" className={btnSecondary} onClick={onDone}>Cancel</button>}
        {save.isError && <span role="alert" className="text-xs text-red-400">{(save.error as Error).message}</span>}
      </div>
      <p className="text-[11px] text-ink-500">You record what you already hold or bought elsewhere. The platform never places orders.</p>
    </form>
  );
}
