import { useState } from 'react';
import { ShieldCheck, ShieldOff, Code2, X } from 'lucide-react';
import type { InvestigationBrief } from '../types';

interface Props {
  sqlProof: NonNullable<InvestigationBrief['sql_proof']>;
  onClose: () => void;
}

export function SqlGrainProofDrawer({ sqlProof, onClose }: Props) {
  const [dialect, setDialect] = useState<'duckdb' | 'postgres'>('duckdb');
  const safeDisplay = dialect === 'postgres' && sqlProof.postgres_sql ? sqlProof.postgres_sql : sqlProof.safe_sql;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end">
      <div className="w-full max-w-2xl bg-slate-950 border-l border-slate-800 h-full overflow-y-auto p-6 space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2">
            <Code2 className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-semibold text-white">Verified SQL &amp; Grain Proof</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {sqlProof.guard_result.fan_out_detected && (
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/40 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-300">
                1:N Join Fan-Out Detected &amp; Neutralized
              </span>
              {sqlProof.inflation_factor && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-red-500/20 text-red-300">
                  {sqlProof.inflation_factor}x Inflation Prevented
                </span>
              )}
            </div>
            {sqlProof.guard_result.fan_out_issues.map((issue, idx) => (
              <p key={idx} className="text-xs text-slate-300">
                {issue.message}
              </p>
            ))}
          </div>
        )}

        {sqlProof.naive_sql && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-400">
                <ShieldOff className="w-4 h-4" />
                Naive Unchecked SQL [Blocked Fan-Out]
              </span>
              {sqlProof.naive_result != null && (
                <span className="text-sm font-mono font-bold text-red-400 line-through">
                  ${sqlProof.naive_result.toLocaleString()}
                </span>
              )}
            </div>
            <pre className="p-3.5 rounded-lg bg-red-950/20 border border-red-500/30 text-[11px] font-mono text-red-200 overflow-x-auto">
              {sqlProof.naive_sql}
            </pre>
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
              Grain-Safe Verified SQL
            </span>
            <div className="flex items-center gap-2">
              {sqlProof.safe_result != null && (
                <span className="text-sm font-mono font-bold text-emerald-400">
                  ${sqlProof.safe_result.toLocaleString()}
                </span>
              )}
              <div className="inline-flex rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-[11px]">
                <button
                  onClick={() => setDialect('duckdb')}
                  className={`px-2 py-0.5 rounded cursor-pointer ${
                    dialect === 'duckdb' ? 'bg-sky-500 text-white' : 'text-slate-400'
                  }`}
                >
                  DuckDB
                </button>
                <button
                  onClick={() => setDialect('postgres')}
                  className={`px-2 py-0.5 rounded cursor-pointer ${
                    dialect === 'postgres' ? 'bg-sky-500 text-white' : 'text-slate-400'
                  }`}
                >
                  Postgres
                </button>
              </div>
            </div>
          </div>
          <pre className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-[11px] font-mono text-emerald-100 overflow-x-auto">
            {safeDisplay}
          </pre>
        </div>

        {sqlProof.guard_result.explain_plan && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-slate-400">DuckDB EXPLAIN Cost Guard</div>
            <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[10px] font-mono text-slate-300 overflow-x-auto max-h-48">
              {sqlProof.guard_result.explain_plan}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
