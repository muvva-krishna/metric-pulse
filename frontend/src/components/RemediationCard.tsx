import { useState } from 'react';
import { FileCode2, ShieldAlert } from 'lucide-react';
import type { RemediationArtifact } from '../types';

interface Props {
  remediation: RemediationArtifact;
}

export function RemediationCard({ remediation }: Props) {
  const [tab, setTab] = useState<'dbt_patch' | 'backfill_sql' | 'quarantine_sql'>('dbt_patch');

  return (
    <div className="rounded-xl bg-red-950/20 border border-red-500/40 p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <FileCode2 className="w-4 h-4 text-red-400" />
            Automated FDE Remediation Artifacts ({remediation.target_model})
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Ready-to-commit dbt schema contract patch and idempotent DuckDB/Postgres replay SQL.
          </p>
        </div>

        <div className="inline-flex rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
          <button
            onClick={() => setTab('dbt_patch')}
            className={`px-2.5 py-1 rounded cursor-pointer ${
              tab === 'dbt_patch' ? 'bg-red-500/30 text-red-200 font-semibold' : 'text-slate-400'
            }`}
          >
            dbt schema.yml Patch
          </button>
          <button
            onClick={() => setTab('backfill_sql')}
            className={`px-2.5 py-1 rounded cursor-pointer ${
              tab === 'backfill_sql' ? 'bg-red-500/30 text-red-200 font-semibold' : 'text-slate-400'
            }`}
          >
            Idempotent MERGE Backfill
          </button>
          <button
            onClick={() => setTab('quarantine_sql')}
            className={`px-2.5 py-1 rounded cursor-pointer ${
              tab === 'quarantine_sql' ? 'bg-red-500/30 text-red-200 font-semibold' : 'text-slate-400'
            }`}
          >
            Quarantine SQL
          </button>
        </div>
      </div>

      <pre className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-emerald-200 overflow-x-auto">
        {tab === 'dbt_patch'
          ? remediation.dbt_schema_patch_yaml
          : tab === 'backfill_sql'
          ? remediation.backfill_sql
          : remediation.quarantine_sql}
      </pre>

      <div className="space-y-1.5 pt-1">
        <div className="text-xs font-semibold text-red-300 flex items-center gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5" />
          Incident Recovery Runbook
        </div>
        {remediation.incident_runbook.map((step, i) => (
          <div key={i} className="text-xs text-slate-300 font-mono">
            {step}
          </div>
        ))}
      </div>
    </div>
  );
}
