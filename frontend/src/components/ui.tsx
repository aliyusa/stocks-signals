import type { ReactNode } from "react";

export function Card({ title, action, children, className = "" }: {
  title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-xl border border-ink-800 bg-ink-900 ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-700 px-4 py-8 text-center">
      <p className="text-sm font-medium text-ink-300">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-ink-400">{children}</div>}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900 p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-ink-400">{label}</p>
      <p className="num mt-2 text-2xl font-semibold text-ink-100">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export const DISCLAIMER =
  "This platform provides market research, technical analysis and Shariah-screening information for educational " +
  "and decision-support purposes. Signals are not guarantees of future performance and are not personalised " +
  "investment advice. Users are responsible for their own investment decisions. Shariah screening methodologies " +
  "differ; verify religious compliance with an appropriately qualified authority.";

export function Disclaimer() {
  return <p className="text-[11px] leading-relaxed text-ink-500">{DISCLAIMER}</p>;
}
