import { Sparkles } from 'lucide-react';
import type { KitagawaDecomposition } from '../types';

interface Props {
  kitagawa: KitagawaDecomposition;
}

export function SimpsonsParadoxCard({ kitagawa }: Props) {
  if (!kitagawa.simpsons_paradox) return null;

  return (
    <div className="rounded-xl bg-violet-950/35 border border-violet-500/50 p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-200 border border-violet-500/40">
            <Sparkles className="w-3.5 h-3.5" />
            SIMPSON&apos;S PARADOX ALERT (Kitagawa-Oaxaca Decomposition)
          </span>
          <p className="text-sm text-slate-200 mt-2">{kitagawa.explanation}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
          <div className="text-slate-400">Aggregate Change</div>
          <div className="text-lg font-bold text-rose-400 mt-0.5">
            {(kitagawa.total_change * 100).toFixed(2)}pp
          </div>
        </div>
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
          <div className="text-slate-400">Within-Segment Rate Effect</div>
          <div className="text-lg font-bold text-emerald-400 mt-0.5">
            +{(kitagawa.within_segment_effect * 100).toFixed(2)}pp
          </div>
        </div>
        <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
          <div className="text-slate-400">Traffic Mix-Shift Effect</div>
          <div className="text-lg font-bold text-violet-300 mt-0.5">
            {(kitagawa.mix_shift_effect * 100).toFixed(2)}pp
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400">
              <th className="py-2 pr-3">Segment</th>
              <th className="py-2 pr-3">Baseline Rate</th>
              <th className="py-2 pr-3">Current Rate</th>
              <th className="py-2 pr-3">Rate Delta</th>
              <th className="py-2 pr-3">Volume Share Shift</th>
            </tr>
          </thead>
          <tbody>
            {kitagawa.segment_details.map((s) => (
              <tr key={s.segment} className="border-b border-slate-800/60 text-slate-200">
                <td className="py-2 pr-3 font-mono font-semibold">{s.segment}</td>
                <td className="py-2 pr-3">{(s.baseline_rate * 100).toFixed(1)}%</td>
                <td className="py-2 pr-3">{(s.current_rate * 100).toFixed(1)}%</td>
                <td className="py-2 pr-3 text-emerald-400 font-semibold">
                  +{(s.rate_delta_pp * 100).toFixed(2)}pp
                </td>
                <td className="py-2 pr-3 font-mono">
                  {(s.baseline_share * 100).toFixed(1)}% → {(s.current_share * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
