import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "../lib/api";
import type { AlertEventRow } from "../lib/types";

/** Header bell: polls for unread alert events every minute and shows a browser notification for new
 *  ones on alerts that asked for it (only while the app is open; no background push service). */
export default function AlertBell() {
  const qc = useQueryClient();
  const seen = useRef<number | null>(null);
  const q = useQuery({
    queryKey: ["alert-unread"],
    queryFn: () => api<{ events: AlertEventRow[] }>("/api/alerts/events?unread_only=true&limit=50"),
    refetchInterval: 60_000,
  });
  const events = q.data?.events ?? [];
  useEffect(() => {
    if (!q.data) return;
    const maxId = events.reduce((m, e) => Math.max(m, e.id), 0);
    if (seen.current === null) { seen.current = maxId; return; }
    const fresh = events.filter((e) => e.id > (seen.current ?? 0));
    if (fresh.length) {
      seen.current = maxId;
      for (const k of ["alerts", "alert-events", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
      if (typeof Notification !== "undefined" && Notification.permission === "granted")
        fresh.filter((e) => e.browser).forEach((e) => new Notification(e.payload.title, { body: e.payload.message, tag: `hss-${e.id}` }));
    }
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const n = events.length;
  return (
    <Link to="/alerts" className="relative rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100" aria-label={`Alerts, ${n} unread`} title="Alerts">
      <Bell size={16} />
      {n > 0 && <span className="num absolute -right-0.5 -top-0.5 min-w-[16px] rounded-full bg-brand-600 px-1 text-center text-[10px] font-semibold leading-4 text-white">{n > 9 ? "9+" : n}</span>}
    </Link>
  );
}
