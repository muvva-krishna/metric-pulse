import { useEffect, useState } from 'react';
import { ShieldAlert, ShieldCheck, Play, GitFork, Code2 } from 'lucide-react';
import type { JoinEdgeAnalysis, SqlPreset } from '../types';

export function SqlWorkbench() {
  const [presets, setPresets] = useState<SqlPreset[]>([]);
  const [activePresetId, setActivePresetId] = useState<string>('');
  const [sql, setSql] = useState<string>('');
  const [targetDialect, setTargetDialect] = useState<'duckdb' | 'postgres' | 'snowflake' | 'bigquery'>('duckdb');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    guard_result: {
      allowed: boolean;
      status: string;
      original_sql: string;
      safe_sql: string;
      fan_out_detected: boolean;
      chasm_trap_detected: boolean;
      left_join_trap_repaired: boolean;
      fan_out_issues: JoinEdgeAnalysis[];
      join_graph: JoinEdgeAnalysis[];
      warnings: string[];
      explain_plan: string;
      error?: string | null;
    };
    transpiled_dialects: Record<string, string>;
    rows: Array<Record<string, unknown>>;
    naive_rows: Array<Record<string, unknown>>;
  } | null>(null);

  useEffect(() => {
    fetch('/api/sql/presets')
      .then((r) => r.json())
      .then((d) => {
        const list: SqlPreset[] = d.presets || [];
        setPresets(list);
        if (list.length > 0) {
          setActivePresetId(list[0].id);
          setSql(list[0].sql);
          runInspect(list[0].sql);
        }
      })
      .catch(console.error);
  }, []);

  async function runInspect(queryToRun: string) {
    setLoading(true);
    try {
      const res = await fetch('/api/sql/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sql: queryToRun,
          dialect: 'duckdb',
          target_dialect: 'postgres',
          strict_partition: true,
          execute: true,
        }),
      });
      const data = await res.json();
      setResult(data);
    } finally {
      setLoading(false);
    }
  }

  const displayedSafeSql =
    targetDialect === 'duckdb'
      ? result?.guard_result.safe_sql
      : result?.transpiled_dialects?.[targetDialect] || result?.guard_result.safe_sql;

  return (
    <div className="space-y-5">
      <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Code2 className="w-5 h-5 text-sky-400" />
              Interactive sqlglot AST Firewall &amp; Join-Cardinality Workbench
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Test arbitrary SQL against dbt manifest.json grains: 1:N Fan-Outs, N:M Chasm Traps, LEFT JOIN Null-Rejection Traps, and Partition/DDL guards.
            </p>
          </div>
          <button
            onClick={() => runInspect(sql)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-xs font-semibold text-slate-950 cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            Inspect &amp; Compile AST
          </button>
        </div>

        {/* Presets */}
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                setActivePresetId(p.id);
                setSql(p.sql);
                runInspect(p.sql);
              }}
              className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition cursor-pointer ${
                activePresetId === p.id
                  ? 'bg-sky-500/20 border-sky-400 text-sky-200'
                  : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
              }`}
            >
              {p.title}
            </button>
          ))}
        </div>

        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          rows={7}
          className="w-full p-3.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-100 focus:outline-none focus:border-sky-500"
        />
      </div>

      {result && (
        <div className="space-y-5">
          {/* Status Banner */}
          <div
            className={`rounded-xl p-4 border ${
              !result.guard_result.allowed
                ? 'bg-red-950/35 border-red-500/50 text-red-200'
                : result.guard_result.chasm_trap_detected ||
                  result.guard_result.fan_out_detected ||
                  result.guard_result.left_join_trap_repaired
                ? 'bg-amber-950/30 border-amber-500/50 text-amber-100'
                : 'bg-emerald-950/30 border-emerald-500/40 text-emerald-100'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold flex items-center gap-2">
                {result.guard_result.allowed ? (
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                ) : (
                  <ShieldAlert className="w-4 h-4 text-red-400" />
                )}
                AST VERDICT: {result.guard_result.status}
              </span>
            </div>
            {result.guard_result.error && (
              <p className="text-xs font-mono text-red-300 mt-2">{result.guard_result.error}</p>
            )}
            {result.guard_result.warnings?.map((w, i) => (
              <p key={i} className="text-xs font-mono text-amber-300 mt-1.5">
                • {w}
              </p>
            ))}
            {result.guard_result.fan_out_issues?.map((issue, i) => (
              <p key={i} className="text-xs font-mono text-amber-200 mt-1.5">
                • [{issue.cardinality}] {issue.message}
              </p>
            ))}
          </div>

          {/* Join Cardinality Graph */}
          {result.guard_result.join_graph && result.guard_result.join_graph.length > 0 && (
            <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-2.5">
              <div className="text-xs font-semibold text-white flex items-center gap-2">
                <GitFork className="w-4 h-4 text-sky-400" />
                Join-Edge Cardinality Classification (vs. dbt manifest.json primary keys)
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {result.guard_result.join_graph.map((edge, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono flex items-center justify-between"
                  >
                    <div>
                      <span className="text-sky-300">{edge.left_table}</span> ({edge.left_grain}) ⋈{' '}
                      <span className="text-amber-300">{edge.right_table}</span> ({edge.right_grain}) ON{' '}
                      <span className="text-white">{edge.join_key}</span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        edge.is_safe ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                      }`}
                    >
                      {edge.cardinality} → {edge.rewrite_action}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Side-by-Side SQL & Execution Comparison */}
          {result.guard_result.allowed && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-red-300">
                    Input / Unchecked SQL
                  </span>
                  {result.naive_rows.length > 0 && (
                    <span className="text-xs font-mono text-red-400">
                      Unchecked Result: {JSON.stringify(result.naive_rows[0])}
                    </span>
                  )}
                </div>
                <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300 overflow-x-auto">
                  {result.guard_result.original_sql}
                </pre>
              </div>

              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-emerald-300">
                    Compiled Grain-Safe SQL
                  </span>
                  <div className="inline-flex rounded-lg bg-slate-950 border border-slate-800 p-0.5 text-[11px]">
                    {(['duckdb', 'postgres', 'snowflake', 'bigquery'] as const).map((d) => (
                      <button
                        key={d}
                        onClick={() => setTargetDialect(d)}
                        className={`px-2 py-0.5 rounded uppercase cursor-pointer ${
                          targetDialect === d ? 'bg-sky-500 text-slate-950 font-bold' : 'text-slate-400'
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>
                {result.rows.length > 0 && (
                  <div className="text-xs font-mono text-emerald-400">
                    Verified Result: {JSON.stringify(result.rows[0])}
                  </div>
                )}
                <pre className="p-3 rounded-lg bg-slate-950 border border-emerald-500/30 text-[11px] font-mono text-emerald-200 overflow-x-auto">
                  {displayedSafeSql}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
