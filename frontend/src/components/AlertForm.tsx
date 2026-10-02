import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AlertOptions, StockRef } from "../lib/types";
import { btnPrimary, inputCls } from "./ShariahPanel";
import StockPicker from "./StockPicker";

const CHANNEL_LABEL: Record<string, string> = { in_app: "In the app", browser: "Browser notification", email: "Email" };
const COOLDOWNS: [number, string][] = [[60, "1 hour"], [240, "4 hours"], [1440, "1 day"], [4320, "3 days"], [10080, "1 week"]];

export function useAlertOptions() {
  return useQuery({ queryKey: ["alert-options"], queryFn: () => api<AlertOptions>("/api/alerts/options"), staleTime: 5 * 60_000 });
}

export default function AlertForm({ stock, onDone }: { stock?: StockRef; onDone?: () => void }) {
  const qc = useQueryClient();
  const opts = useAlertOptions();
  const [pick, setPick] = useState<StockRef | null>(stock ?? null);
  const [type, setType] = useState("price_above");
  const [param, setParam] = useState("");
  const [signal, setSignal] = useState("BUY_SETUP");
  const [channels, setChannels] = useState<string[]>(["in_app", "browser"]);
  const [cooldown, setCooldown] = useState(1440);
  const [name, setName] = useState("");
  const spec = opts.data?.conditions.find((c) => c.type === type);
  const create = useMutation({
    mutationFn: () => api("/api/alerts", {
      method: "POST",
      body: JSON.stringify({
        exchange: pick!.exchange, ticker: pick!.ticker, name: name || null, channels, cooldown_minutes: cooldown,
        condition: { type, ...(spec?.param === "level" ? { level: Number(param) } : spec?.param === "value" ? { value: Number(param) } : spec?.param === "signal" ? { signal } : {}) },
      }),
    }),
    onSuccess: () => {
      setParam(""); setName("");
      for (const k of ["alerts", "alert-events", "membership", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
      onDone?.();
    },
  });
  if (!opts.data) return <p className="text-xs text-ink-400">Loading…</p>;
  const needsNum = spec?.param === "level" || spec?.param === "value";
  const ok = pick && (!needsNum || (param !== "" && Number(param) > 0));

  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (ok) create.mutate(); }}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        {!stock && <StockPicker value={pick} onChange={setPick} />}
        <label className="text-[11px] text-ink-400 sm:col-span-2">Condition
          <select className={inputCls} value={type} onChange={(e) => { setType(e.target.value); setParam(""); }}>
            {opts.data.conditions.map((c) => <option key={c.type} value={c.type}>{c.label}</option>)}
          </select>
        </label>
        {needsNum && (
          <label className="text-[11px] text-ink-400">{spec?.param === "level" ? "Price" : "Value (0 to 100)"}
            <input className={`${inputCls} num`} type="number" step="any" min={0} max={spec?.param === "value" ? 100 : undefined} required
              value={param} onChange={(e) => setParam(e.target.value)} />
          </label>
        )}
        {spec?.param === "signal" && (
          <label className="text-[11px] text-ink-400">Signal
            <select className={inputCls} value={signal} onChange={(e) => setSignal(e.target.value)}>
              {opts.data.signal_types.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
            </select>
          </label>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <label className="text-[11px] text-ink-400 sm:col-span-2">Name (optional)
          <input className={inputCls} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. DANGCEM breakout" />
        </label>
        <label className="text-[11px] text-ink-400">Repeat at most every
          <select className={inputCls} value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))}>
            {COOLDOWNS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      </div>
      <fieldset className="flex flex-wrap gap-4">
        <legend className="mb-1 text-[11px] uppercase tracking-wider text-ink-500">Notify me</legend>
        {Object.entries(CHANNEL_LABEL).map(([k, l]) => {
          const available = opts.data!.channels[k];
          return (
            <label key={k} className={`inline-flex items-center gap-2 text-xs ${available ? "text-ink-300" : "text-ink-500"}`}
              title={available ? undefined : "Email is not configured on the server"}>
              <input type="checkbox" className="accent-teal-500" disabled={k === "in_app" || !available}
                checked={k === "in_app" || channels.includes(k)}
                onChange={() => setChannels(channels.includes(k) ? channels.filter((x) => x !== k) : [...channels, k])} />
              {l}{!available && " (not configured)"}
            </label>
          );
        })}
      </fieldset>
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={btnPrimary} disabled={!ok || create.isPending}>Create alert</button>
        {create.isError && <span role="alert" className="text-xs text-red-400">{(create.error as Error).message}</span>}
        {create.isSuccess && <span className="text-xs text-emerald-400">Alert created and checked on the latest stored data.</span>}
      </div>
    </form>
  );
}
