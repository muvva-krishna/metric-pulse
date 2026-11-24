import { Terminal, CheckCircle2, Wrench, ShieldAlert } from 'lucide-react';
import type { TraceStep } from '../types';

interface Props {
  trace: TraceStep[];
}

export function ExecutionTraceBar({ trace }: Props) {
  if (!trace || trace.length === 0) return null;

  const totalMs = trace.reduce((acc, s) => acc + s.duration_ms, 0);

  return (
    <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
          <Terminal className="w-4 h-4 text-sky-400" />
          Deterministic Compiler &amp; Execution Telemetry Trace
        </div>
        <span className="text-[11px] font-mono text-slate-400">
          {trace.length} stages · {totalMs.toFixed(1)}ms total
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        {trace.map((step, idx) => {
          const isIncident = step.status === 'INCIDENT';
          const isRewritten = step.status === 'REWRITTEN' || step.status === 'ACTION_REQUIRED';
          return (
            <div
              key={`${step.stage}-${idx}`}
              className={`rounded-lg p-3 border text-xs ${
                isIncident
                  ? 'bg-red-950/30 border-red-500/40'
                  : isRewritten
                  ? 'bg-amber-950/25 border-amber-500/40'
                  : 'bg-slate-950/70 border-slate-800/80'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-semibold text-white flex items-center gap-1.5">
                  {isIncident ? (
                    <ShieldAlert className="w-3.5 h-3.5 text-red-400 shrink-0" />
                  ) : isRewritten ? (
                    <Wrench className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  )}
                  {step.title}
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-900 text-sky-300 border border-slate-800">
                  {step.duration_ms.toFixed(1)}ms
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono leading-relaxed">{step.detail}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
