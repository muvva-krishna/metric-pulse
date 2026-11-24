import { BarChart3, Filter } from 'lucide-react';
import type { SegmentAttribution } from '../types';

interface Props {
  cohorts: SegmentAttribution[];
  baselineRate: number;
  currentRate: number;
  testedCohorts?: number;
  significantCohorts?: number;
  noiseSuppressedCohorts?: number;
}

export function ContributionWaterfall({
  cohorts,
  baselineRate,
  currentRate,
  testedCohorts,
  significantCohorts,
  noiseSuppressedCohorts,
}: Props) {
  const maxAbs = Math.max(...cohorts.map((c) => Math.abs(c.contribution_pct)), 10);

  return (
    <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-sky-400" />
            Contribution-to-Change Waterfall (Benjamini-Hochberg FDR Controlled)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Baseline {(baselineRate * 100).toFixed(1)}% → Current {(currentRate * 100).toFixed(1)}%
          </p>
        </div>

        {testedCohorts != null && (
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              {significantCohorts} Significant (q≤0.05)
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1">
              <Filter className="w-3 h-3" />
              {noiseSuppressedCohorts} Noise-Suppressed / {testedCohorts} Tested
            </span>
          </div>
        )}
      </div>

      <div className="space-y-3.5">
        {cohorts.map((c, idx) => {
          const widthPct = Math.min(100, Math.max(4, (Math.abs(c.contribution_pct) / maxAbs) * 100));
          const isTop = idx === 0;
          const isSig = c.is_significant !== false;
          return (
            <div key={c.segment} className="space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className={`font-mono ${isTop ? 'text-rose-300 font-semibold' : 'text-slate-300'}`}>
                    {c.segment}
                  </span>
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      isSig
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {isSig ? `BH-FDR q=${(c.q_value ?? 0).toFixed(4)} · z=${c.z_score ?? 0}` : 'NOISE SUPPRESSED'}
                  </span>
                </div>
                <span className="text-slate-400 font-mono">
                  {(c.baseline_value * 100).toFixed(1)}% → {(c.current_value * 100).toFixed(1)}% (n={c.current_volume}) ·{' '}
                  <span className={isTop ? 'text-rose-400 font-bold' : 'text-slate-200'}>
                    {c.contribution_pct.toFixed(1)}% of change
                  </span>
                </span>
              </div>
              <div className="h-2.5 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    isTop
                      ? 'bg-gradient-to-r from-rose-500 to-amber-500'
                      : isSig
                      ? 'bg-sky-500/80'
                      : 'bg-slate-600/50'
                  }`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
