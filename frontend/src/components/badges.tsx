import type { DataStatus, ShariahStatus, SignalType } from "../lib/types";

const base = "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide ring-1 ring-inset";

const DATA: Record<DataStatus, [string, string]> = {
  LIVE: ["LIVE", "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"],
  DELAYED: ["DELAYED", "bg-sky-500/10 text-sky-300 ring-sky-500/30"],
  END_OF_DAY: ["END-OF-DAY", "bg-indigo-500/10 text-indigo-300 ring-indigo-500/30"],
  STALE: ["STALE", "bg-amber-500/10 text-amber-300 ring-amber-500/30"],
  UNAVAILABLE: ["UNAVAILABLE", "bg-ink-700/60 text-ink-300 ring-ink-500/40"],
};

export function DataStatusBadge({ status, title }: { status: DataStatus; title?: string }) {
  const [label, cls] = DATA[status];
  return (
    <span className={`${base} ${cls}`} title={title}>
      <span className={`h-1.5 w-1.5 rounded-full ${status === "LIVE" ? "animate-pulse bg-emerald-400" : "bg-current opacity-70"}`} />
      {label}
    </span>
  );
}

const SHARIAH: Record<ShariahStatus, [string, string]> = {
  COMPLIANT: ["COMPLIANT", "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"],
  NON_COMPLIANT: ["NON-COMPLIANT", "bg-red-500/10 text-red-300 ring-red-500/30"],
  QUESTIONABLE: ["QUESTIONABLE", "bg-amber-500/10 text-amber-300 ring-amber-500/30"],
  INSUFFICIENT_DATA: ["INSUFFICIENT DATA", "bg-ink-700/60 text-ink-300 ring-ink-500/40"],
  UNDER_REVIEW: ["UNDER REVIEW", "bg-violet-500/10 text-violet-300 ring-violet-500/30"],
  NOT_SCREENED: ["NOT SCREENED", "bg-ink-800 text-ink-300 ring-ink-700"],
};

export function ShariahBadge({ status, title }: { status: ShariahStatus; title?: string }) {
  const [label, cls] = SHARIAH[status] ?? SHARIAH.NOT_SCREENED;
  return <span className={`${base} ${cls}`} title={title}>{label}</span>;
}

const SIGNAL: Record<SignalType, [string, string]> = {
  BUY_SETUP: ["POTENTIAL BUY SETUP", "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"],
  SELL_EXIT: ["SELL / EXIT", "bg-red-500/10 text-red-300 ring-red-500/30"],
  HOLD: ["HOLD", "bg-sky-500/10 text-sky-300 ring-sky-500/30"],
  WAIT: ["WAIT", "bg-ink-700/60 text-ink-300 ring-ink-500/40"],
  AVOID: ["AVOID", "bg-red-500/10 text-red-300 ring-red-500/30"],
  WATCHLIST: ["WATCHLIST", "bg-amber-500/10 text-amber-300 ring-amber-500/30"],
};

export function SignalBadge({ type }: { type: SignalType }) {
  const [label, cls] = SIGNAL[type];
  return <span className={`${base} ${cls}`}>{label}</span>;
}
