import { useEffect, useState } from 'react';
import { Activity, Code2, Search, ShieldAlert, CheckCircle2, Sparkles, Loader2, Terminal } from 'lucide-react';
import type { AnomalyCard, InvestigationBrief } from './types';
import { KpiAnomalyGrid } from './components/KpiAnomalyGrid';
import { LineageDag } from './components/LineageDag';
import { ContributionWaterfall } from './components/ContributionWaterfall';
import { SimpsonsParadoxCard } from './components/SimpsonsParadoxCard';
import { SqlGrainProofDrawer } from './components/SqlGrainProofDrawer';
import { ExecutionTraceBar } from './components/ExecutionTraceBar';
import { RemediationCard } from './components/RemediationCard';
import { SqlWorkbench } from './components/SqlWorkbench';

export default function App() {
  const [viewMode, setViewMode] = useState<'rca' | 'workbench'>('rca');
  const [anomalies, setAnomalies] = useState<AnomalyCard[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [brief, setBrief] = useState<InvestigationBrief | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    fetch('/api/anomalies')
      .then((r) => r.json())
      .then((d) => {
        const list: AnomalyCard[] = d.anomalies || [];
        setAnomalies(list);
        if (list.length > 0) {
          runInvestigation(list[0].question, list[0].id);
        }
      })
      .catch(console.error);
  }, []);

  async function runInvestigation(q: string, scenarioId?: string) {
    setLoading(true);
    if (scenarioId) setActiveId(scenarioId);
    try {
      const res = await fetch('/api/investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, scenario_id: scenarioId }),
      });
      const data: InvestigationBrief = await res.json();
      setBrief(data);
      setActiveId(data.scenario_id);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setViewMode('rca');
    runInvestigation(question.trim());
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/20 border border-sky-400/40 flex items-center justify-center">
                <Activity className="w-4 h-4 text-sky-400" />
              </div>
              <div>
                <h1 className="text-base font-bold tracking-tight text-white">MetricPulse</h1>
                <p className="text-[11px] text-slate-400">
                  Autonomous Enterprise RCA · dbt Semantic Compiler + sqlglot AST Firewall
                </p>
              </div>
            </div>

            <div className="inline-flex rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs">
              <button
                onClick={() => setViewMode('rca')}
                className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer ${
                  viewMode === 'rca' ? 'bg-sky-500 text-slate-950 font-semibold' : 'text-slate-400 hover:text-white'
                }`}
              >
                Executive RCA Console
              </button>
              <button
                onClick={() => setViewMode('workbench')}
                className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer flex items-center gap-1.5 ${
                  viewMode === 'workbench'
                    ? 'bg-sky-500 text-slate-950 font-semibold'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                SQL AST Firewall Workbench
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="flex-1 max-w-xl flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask why any metric moved (e.g., Why did EU Checkout Conversion drop?)"
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="px-3.5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-xs font-semibold text-slate-950 transition cursor-pointer disabled:opacity-50"
            >
              Investigate
            </button>
          </form>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {viewMode === 'workbench' ? (
          <SqlWorkbench />
        ) : (
          <>
            <KpiAnomalyGrid
              anomalies={anomalies}
              activeId={activeId}
              onSelect={(a) => {
                setQuestion(a.question);
                runInvestigation(a.question, a.id);
              }}
            />

            {loading && (
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-8 flex items-center justify-center gap-3 text-sm text-sky-300">
                <Loader2 className="w-5 h-5 animate-spin" />
                Running 4-stage autonomous investigation (Semantic Compiler → Triage Gate → sqlglot Firewall → BH-FDR Attribution)...
              </div>
            )}

            {!loading && brief && (
              <div className="space-y-5">
                {brief.trace && <ExecutionTraceBar trace={brief.trace} />}

                {/* Executive Verdict Banner */}
                <div
                  className={`rounded-xl p-5 border ${
                    brief.verdict_type === 'PIPELINE_INCIDENT'
                      ? 'bg-red-950/30 border-red-500/50'
                      : brief.verdict_type === 'FAN_OUT_GUARDED'
                      ? 'bg-amber-950/25 border-amber-500/40'
                      : brief.verdict_type === 'SIMPSONS_PARADOX'
                      ? 'bg-violet-950/30 border-violet-500/40'
                      : 'bg-slate-900/80 border-slate-800'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
                    <span
                      className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ${
                        brief.verdict_type === 'PIPELINE_INCIDENT'
                          ? 'bg-red-500/20 text-red-300'
                          : brief.verdict_type === 'SIMPSONS_PARADOX'
                          ? 'bg-violet-500/20 text-violet-200'
                          : 'bg-emerald-500/15 text-emerald-300'
                      }`}
                    >
                      {brief.verdict_type === 'PIPELINE_INCIDENT' ? (
                        <ShieldAlert className="w-3.5 h-3.5" />
                      ) : brief.verdict_type === 'SIMPSONS_PARADOX' ? (
                        <Sparkles className="w-3.5 h-3.5" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      {brief.verdict_badge}
                    </span>

                    {brief.sql_proof && (
                      <button
                        onClick={() => setDrawerOpen(true)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-sky-300 cursor-pointer"
                      >
                        <Code2 className="w-3.5 h-3.5" />
                        Verified SQL &amp; Grain Proof
                      </button>
                    )}
                  </div>

                  <h2 className="text-lg font-bold text-white">{brief.headline}</h2>
                  <p className="mt-2 text-sm text-slate-300 leading-relaxed">{brief.executive_summary}</p>
                  <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300">
                    <span className="font-semibold text-sky-300">Recommended Action:</span>{' '}
                    {brief.recommended_action}
                  </div>
                </div>

                {brief.remediation && <RemediationCard remediation={brief.remediation} />}

                {brief.attribution?.kitagawa && (
                  <SimpsonsParadoxCard kitagawa={brief.attribution.kitagawa} />
                )}

                {brief.attribution?.top_cohorts && brief.attribution.top_cohorts.length > 0 && (
                  <ContributionWaterfall
                    cohorts={brief.attribution.top_cohorts}
                    baselineRate={brief.attribution.overall.baseline_rate}
                    currentRate={brief.attribution.overall.current_rate}
                    testedCohorts={brief.attribution.overall.tested_cohorts}
                    significantCohorts={brief.attribution.overall.significant_cohorts}
                    noiseSuppressedCohorts={brief.attribution.overall.noise_suppressed_cohorts}
                  />
                )}

                <LineageDag nodes={brief.lineage.nodes} edges={brief.lineage.edges} />
              </div>
            )}
          </>
        )}
      </main>

      {drawerOpen && brief?.sql_proof && (
        <SqlGrainProofDrawer sqlProof={brief.sql_proof} onClose={() => setDrawerOpen(false)} />
      )}
    </div>
  );
}
