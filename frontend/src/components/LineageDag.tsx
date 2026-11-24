import { useState } from 'react';
import { CheckCircle2, XCircle, Database, ArrowRight } from 'lucide-react';
import type { LineageEdge, LineageNode } from '../types';

interface Props {
  nodes: LineageNode[];
  edges: LineageEdge[];
}

const TIER_LABELS: Record<number, string> = {
  0: 'Raw Sources',
  1: 'Staging (dbt)',
  2: 'Intermediate',
  3: 'Mart',
};

export function LineageDag({ nodes, edges }: Props) {
  const [selected, setSelected] = useState<LineageNode | null>(null);

  const layers = [0, 1, 2, 3]
    .map((layer) => ({
      layer,
      title: TIER_LABELS[layer],
      items: nodes.filter((n) => n.layer === layer),
    }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Database className="w-4 h-4 text-sky-400" />
            dbt Upstream Lineage &amp; Pipeline Health DAG
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Click any node to inspect grain metadata, freshness SLA, volume z-score, and NULL checks.
          </p>
        </div>
        <span className="text-[11px] font-mono text-slate-400">
          {nodes.length} nodes · {edges.length} edges
        </span>
      </div>

      <div className="flex flex-col md:flex-row items-stretch gap-3 overflow-x-auto pb-2">
        {layers.map((group, idx) => (
          <div key={group.layer} className="flex items-center gap-3 flex-1 min-w-[160px]">
            <div className="flex-1 space-y-2">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                {group.title}
              </div>
              {group.items.map((node) => {
                const isIncident = node.status === 'INCIDENT';
                const isSelected = selected?.id === node.id;
                return (
                  <button
                    key={node.id}
                    onClick={() => setSelected(isSelected ? null : node)}
                    className={`w-full text-left p-2.5 rounded-lg border transition-all cursor-pointer ${
                      isIncident
                        ? 'bg-red-950/60 border-red-500/70 text-red-100 shadow-[0_0_15px_rgba(239,68,68,0.2)]'
                        : 'bg-emerald-950/30 border-emerald-500/30 text-slate-100 hover:border-emerald-400/60'
                    } ${isSelected ? 'ring-2 ring-sky-400' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <span className="text-xs font-mono font-semibold truncate">{node.label}</span>
                      {isIncident ? (
                        <XCircle className="w-4 h-4 text-red-400 shrink-0" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1 font-mono">
                      grain: {node.grain}
                    </div>
                  </button>
                );
              })}
            </div>
            {idx < layers.length - 1 && (
              <ArrowRight className="w-4 h-4 text-slate-600 hidden md:block shrink-0 mt-5" />
            )}
          </div>
        ))}
      </div>

      {selected && (
        <div className="mt-4 p-3.5 rounded-lg bg-slate-950/90 border border-slate-800 text-xs space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-mono font-semibold text-sky-300">{selected.relation_name}</span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                selected.status === 'INCIDENT'
                  ? 'bg-red-500/20 text-red-300'
                  : 'bg-emerald-500/20 text-emerald-300'
              }`}
            >
              {selected.status}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-slate-300 pt-1">
            <div>
              <span className="text-slate-500">Grain:</span>{' '}
              <span className="font-mono">{selected.grain}</span>
            </div>
            <div>
              <span className="text-slate-500">Freshness Lag:</span>{' '}
              <span className="font-mono">
                {selected.diagnostics?.lag_hours != null ? `${selected.diagnostics.lag_hours}h` : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Latest Rows:</span>{' '}
              <span className="font-mono">
                {selected.diagnostics?.latest_row_count ?? 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Volume Z-Score:</span>{' '}
              <span className="font-mono">
                {selected.diagnostics?.volume_z_score ?? 'N/A'}
              </span>
            </div>
          </div>
          {selected.diagnostics?.reasons && selected.diagnostics.reasons.length > 0 && (
            <div className="pt-1 text-red-300">
              {selected.diagnostics.reasons.map((r, i) => (
                <div key={i}>• {r}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
