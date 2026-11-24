import { AlertTriangle, ShieldAlert, GitFork, Sparkles } from 'lucide-react';
import type { AnomalyCard } from '../types';

interface Props {
  anomalies: AnomalyCard[];
  activeId: string | null;
  onSelect: (anomaly: AnomalyCard) => void;
}

const SEVERITY_STYLES: Record<AnomalyCard['severity'], { border: string; badge: string; icon: typeof AlertTriangle }> = {
  critical: {
    border: 'border-rose-500/40 hover:border-rose-400',
    badge: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    icon: AlertTriangle,
  },
  incident: {
    border: 'border-red-500/50 hover:border-red-400',
    badge: 'bg-red-500/20 text-red-300 border-red-500/40',
    icon: ShieldAlert,
  },
  warning: {
    border: 'border-amber-500/40 hover:border-amber-400',
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    icon: GitFork,
  },
  paradox: {
    border: 'border-violet-500/40 hover:border-violet-400',
    badge: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
    icon: Sparkles,
  },
};

export function KpiAnomalyGrid({ anomalies, activeId, onSelect }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {anomalies.map((item) => {
        const style = SEVERITY_STYLES[item.severity];
        const Icon = style.icon;
        const isActive = activeId === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onSelect(item)}
            className={`text-left rounded-xl p-4 bg-slate-900/80 border transition-all cursor-pointer ${
              style.border
            } ${isActive ? 'ring-2 ring-sky-400/70 bg-slate-900' : ''}`}
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full border ${style.badge}`}>
                <Icon className="w-3 h-3" />
                {item.category}
              </span>
              <span className="text-[11px] text-slate-400 font-mono">{item.target_model}</span>
            </div>
            <div className="text-sm font-medium text-slate-300">{item.title}</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-white tracking-tight">{item.headline_value}</span>
              <span className="text-xs font-semibold text-rose-400">{item.headline_delta}</span>
            </div>
            <p className="mt-2 text-xs text-slate-400 line-clamp-2">{item.question}</p>
          </button>
        );
      })}
    </div>
  );
}
