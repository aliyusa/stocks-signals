import { Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { useAuth } from "../lib/auth";
import { Card } from "../components/ui";
import ScoringWeights from "../components/ScoringWeights";

interface Source { code: string; name: string; kind: string; tier: string; frequency: string; website: string | null; notes: string | null; enabled: boolean; last_success_at: string | null; last_error: string | null }
interface Methodology { code: string; name: string; description: string; thresholds: Record<string, number>; prohibited_activities: string[]; denominator: string; max_data_age_days: number }

export default function Settings() {
  const { user } = useAuth();
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/api/data-sources") });
  const meths = useQuery({ queryKey: ["methodologies"], queryFn: () => api<Methodology[]>("/api/shariah/methodologies") });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      <Card title="Account">
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div><dt className="text-xs text-ink-400">Email</dt><dd>{user?.email}</dd></div>
          <div><dt className="text-xs text-ink-400">Name</dt><dd>{user?.full_name ?? "Not set"}</dd></div>
          <div><dt className="text-xs text-ink-400">Time zone</dt><dd>{user?.timezone}</dd></div>
        </dl>
      </Card>

      <ScoringWeights />

      <Card title="Data sources">
        <p className="mb-3 text-xs text-ink-400">API keys are read from the server's environment and are never sent to the browser.</p>
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-ink-500">
              <tr>{["Source", "Kind", "Tier", "Frequency", "Configured", "Last success", "Notes"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {sources.data?.map((s) => (
                <tr key={s.code}>
                  <td className="px-4 py-2.5 font-medium">{s.website ? <a href={s.website} target="_blank" rel="noreferrer" className="hover:text-brand-500">{s.name}</a> : s.name}</td>
                  <td className="px-4 py-2.5 text-ink-300">{s.kind}</td>
                  <td className="px-4 py-2.5 text-ink-300">{s.tier}</td>
                  <td className="px-4 py-2.5 text-ink-300">{s.frequency}</td>
                  <td className="px-4 py-2.5">{s.enabled ? <span className="text-emerald-400">Yes</span> : <span className="text-ink-500">No</span>}</td>
                  <td className="px-4 py-2.5 text-xs text-ink-400">{fmtDateTime(s.last_success_at, "Never")}</td>
                  <td className="px-4 py-2.5 text-xs text-ink-400">{s.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Shariah methodologies">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {meths.data?.map((m) => (
            <div key={m.code} className="rounded-lg border border-ink-800 p-4">
              <p className="text-sm font-semibold">{m.name}</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-400">{m.description}</p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <dt className="text-ink-500">Denominator</dt><dd>{m.denominator.replace(/_/g, " ")}</dd>
                {Object.entries(m.thresholds).map(([k, v]) => (
                  <Fragment key={k}><dt className="text-ink-500">{k.replace(/_/g, " ")}</dt><dd className="num">{(v * 100).toFixed(0)}%</dd></Fragment>
                ))}
                <dt className="text-ink-500">Max data age</dt><dd>{m.max_data_age_days} days</dd>
              </dl>
              <p className="mt-3 text-[11px] text-ink-500">Excluded activities: {m.prohibited_activities.map((a) => a.replace(/_/g, " ")).join(", ")}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[11px] text-ink-500">Editable and custom methodologies arrive in Phase 4. Verify compliance with a qualified Shariah scholar or a recognised screening provider.</p>
      </Card>
    </div>
  );
}
