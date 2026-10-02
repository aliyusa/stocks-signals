import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Check, Minus, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtDateTime } from "../lib/format";
import type { AlertEventRow, AlertRow } from "../lib/types";
import AlertForm, { useAlertOptions } from "../components/AlertForm";
import { btnPrimary, btnSecondary } from "../components/ShariahPanel";
import { Card, EmptyState } from "../components/ui";

const notifyState = () => (typeof Notification === "undefined" ? "unsupported" : Notification.permission);

export default function Alerts() {
  const qc = useQueryClient();
  const opts = useAlertOptions();
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<{ alerts: AlertRow[]; unread: number }>("/api/alerts") });
  const events = useQuery({ queryKey: ["alert-events"], queryFn: () => api<{ events: AlertEventRow[] }>("/api/alerts/events?limit=100") });
  const [perm, setPerm] = useState(notifyState());
  const refresh = () => { for (const k of ["alerts", "alert-events", "dashboard", "membership"]) qc.invalidateQueries({ queryKey: [k] }); };
  const check = useMutation({ mutationFn: () => api<{ fired: number }>("/api/alerts/check", { method: "POST" }), onSuccess: refresh });
  const toggle = useMutation({ mutationFn: (a: AlertRow) => api(`/api/alerts/${a.id}`, { method: "PUT", body: JSON.stringify({ is_active: !a.is_active }) }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: number) => api(`/api/alerts/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/api/alerts/events/read", { method: "POST", body: JSON.stringify({ all: true }) }), onSuccess: refresh });
  const err = check.error ?? toggle.error ?? del.error;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Alerts</h1>
          <p className="max-w-3xl text-xs text-ink-400">{opts.data?.note}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {perm === "default" && (
            <button className={btnSecondary} onClick={async () => setPerm(await Notification.requestPermission())}>
              <BellRing size={12} className="mr-1 inline" />Allow browser notifications
            </button>
          )}
          <button className={btnPrimary} onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? "Checking…" : "Check now"}</button>
        </div>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <div><dt className="inline text-ink-500">Browser notifications: </dt><dd className="inline text-ink-100">{perm === "granted" ? "allowed (shown while the app is open)" : perm === "denied" ? "blocked in your browser settings" : perm === "unsupported" ? "not supported here" : "not yet allowed"}</dd></div>
        <div><dt className="inline text-ink-500">Email: </dt><dd className="inline text-ink-100">{opts.data?.channels.email ? "configured" : "not configured on the server"}</dd></div>
        <div><dt className="inline text-ink-500">Daily job: </dt><dd className="inline text-ink-100">{opts.data?.daily_job ? "on (weekdays, about 20:00 WAT)" : "off (no CRON_SECRET set)"}</dd></div>
        {check.data && <div className="text-emerald-400">Checked: {check.data.fired} fired.</div>}
      </dl>
      {err && <p role="alert" className="text-xs text-red-400">{(err as Error).message}</p>}

      <Card title="New alert"><AlertForm /></Card>

      <Card title={`Your alerts${alerts.data ? ` · ${alerts.data.alerts.length}` : ""}`}>
        {!alerts.data?.alerts.length ? <EmptyState title="No alerts yet">Create one above or from a stock page.</EmptyState> : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm [&_td]:whitespace-nowrap">
              <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
                <tr>{["Stock", "Alert", "Last check", "Channels", "Repeat", "Last fired", ""].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {alerts.data.alerts.map((a) => (
                  <tr key={a.id} className={a.is_active ? "" : "opacity-60"}>
                    <td className="px-4 py-2.5">{a.stock ? <Link to={`/stocks/${a.stock.exchange}/${encodeURIComponent(a.stock.ticker)}`} className="font-medium hover:text-brand-500">{a.stock.ticker}</Link> : "n/a"}</td>
                    <td className="px-4 py-2.5"><p className="text-ink-100">{a.name}</p>{a.name !== a.description && <p className="text-[11px] text-ink-400">{a.description}</p>}</td>
                    <td className="px-4 py-2.5 text-xs">
                      <span className="inline-flex items-center gap-1">
                        {a.last_result === true ? <Check size={12} className="text-emerald-400" aria-label="Condition met" /> : a.last_result === false ? <X size={12} className="text-ink-400" aria-label="Condition not met" /> : <Minus size={12} className="text-ink-500" aria-label="Not evaluated" />}
                        <span className="max-w-[260px] truncate text-ink-300" title={a.last_message ?? ""}>{a.last_message ?? "Not checked yet"}</span>
                      </span>
                      <p className="text-[10px] text-ink-500">{fmtDateTime(a.last_evaluated_at, "Never")}</p>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-300">{a.channels.map((c) => c.replace("_", "-")).join(", ")}</td>
                    <td className="px-4 py-2.5 text-xs text-ink-300">{a.cooldown_minutes >= 1440 ? `${a.cooldown_minutes / 1440} day(s)` : `${a.cooldown_minutes / 60} hour(s)`}</td>
                    <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDateTime(a.last_triggered_at, "Never")}</td>
                    <td className="px-4 py-2.5 text-right text-[11px]">
                      <button className="mr-3 text-ink-300 hover:text-brand-500" onClick={() => toggle.mutate(a)}>{a.is_active ? "Pause" : "Resume"}</button>
                      <button className="text-ink-400 hover:text-red-400" onClick={() => { if (confirm(`Delete the alert "${a.name}"?`)) del.mutate(a.id); }}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Triggered${alerts.data?.unread ? ` · ${alerts.data.unread} unread` : ""}`}
        action={<button className="text-[11px] text-ink-300 hover:text-brand-500 disabled:opacity-40" disabled={!alerts.data?.unread} onClick={() => readAll.mutate()}>Mark all read</button>}>
        {!events.data?.events.length ? <p className="text-xs text-ink-400">Nothing has triggered yet.</p> : (
          <ul className="divide-y divide-ink-800">
            {events.data.events.map((e) => (
              <li key={e.id} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
                <div>
                  <p className={`text-sm ${e.is_read ? "text-ink-300" : "font-medium text-ink-100"}`}>{!e.is_read && <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-brand-500 align-middle" aria-label="Unread" />}{e.payload.title}</p>
                  <p className="text-xs text-ink-400">{e.payload.message}{e.payload.bar_date ? ` · close of ${fmtDate(e.payload.bar_date)}` : ""}</p>
                  <p className="text-[10px] text-ink-500">{Object.entries(e.delivered).map(([k, v]) => `${k.replace("_", "-")}: ${v}`).join(" · ")}</p>
                </div>
                <span className="text-[11px] text-ink-400">{fmtDateTime(e.triggered_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
