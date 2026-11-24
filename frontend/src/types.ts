export interface AnomalyCard {
  id: string;
  title: string;
  question: string;
  metric_label: string;
  headline_value: string;
  headline_delta: string;
  severity: 'critical' | 'incident' | 'warning' | 'paradox';
  target_model: string;
  category: string;
}

export interface TraceStep {
  stage: string;
  title: string;
  duration_ms: number;
  detail: string;
  status: 'OK' | 'INCIDENT' | 'REWRITTEN' | 'ACTION_REQUIRED';
}

export interface RemediationArtifact {
  target_model: string;
  dbt_schema_patch_yaml: string;
  backfill_sql: string;
  quarantine_sql: string;
  incident_runbook: string[];
}

export interface LineageNode {
  id: string;
  unique_id: string;
  label: string;
  tier: 'source' | 'staging' | 'intermediate' | 'mart';
  layer: number;
  relation_name: string;
  grain: string;
  primary_key?: string;
  status: 'HEALTHY' | 'WARNING' | 'INCIDENT';
  diagnostics?: {
    lag_hours?: number;
    freshness_sla_hours?: number;
    latest_row_count?: number;
    baseline_avg_rows?: number;
    volume_z_score?: number;
    null_spikes?: Array<{
      column: string;
      latest_null_pct: number;
      baseline_null_pct: number;
    }>;
    reasons?: string[];
  };
}

export interface LineageEdge {
  source: string;
  target: string;
}

export interface SegmentAttribution {
  dimension: string;
  segment: string;
  baseline_value: number;
  current_value: number;
  baseline_volume: number;
  current_volume: number;
  delta: number;
  impact_score: number;
  contribution_pct: number;
  z_score?: number;
  p_value?: number;
  q_value?: number;
  ci_95?: [number, number];
  is_significant?: boolean;
  significance_label?: string;
}

export interface KitagawaDecomposition {
  overall_baseline_rate: number;
  overall_current_rate: number;
  total_change: number;
  within_segment_effect: number;
  mix_shift_effect: number;
  simpsons_paradox: boolean;
  segment_details: Array<{
    segment: string;
    baseline_rate: number;
    current_rate: number;
    rate_delta_pp: number;
    baseline_share: number;
    current_share: number;
    within_effect: number;
    mix_effect: number;
  }>;
  explanation: string;
}

export interface JoinEdgeAnalysis {
  left_table: string;
  left_grain: string;
  right_table: string;
  right_grain: string;
  join_key: string;
  cardinality: string;
  is_safe: boolean;
  rewrite_action: string;
  message: string;
}

export interface InvestigationBrief {
  scenario_id: string;
  question: string;
  target_model: string;
  verdict_type: 'LOCALIZED_PRODUCT_BUG' | 'PIPELINE_INCIDENT' | 'FAN_OUT_GUARDED' | 'SIMPSONS_PARADOX';
  verdict_badge: string;
  headline: string;
  executive_summary: string;
  recommended_action: string;
  triage: {
    status: string;
    summary: string;
    broken_nodes: Array<Record<string, unknown>>;
    node_health: Record<string, unknown>;
  };
  remediation?: RemediationArtifact | null;
  lineage: {
    nodes: LineageNode[];
    edges: LineageEdge[];
  };
  attribution?: {
    overall: {
      baseline_rate: number;
      current_rate: number;
      delta_pp: number;
      relative_change_pct: number;
      baseline_volume: number;
      current_volume: number;
      tested_cohorts?: number;
      significant_cohorts?: number;
      noise_suppressed_cohorts?: number;
    };
    top_cohorts: SegmentAttribution[];
    single_dimensions: SegmentAttribution[];
    kitagawa: KitagawaDecomposition;
  } | null;
  sql_proof?: {
    naive_sql?: string;
    naive_result?: number;
    safe_sql: string;
    safe_result?: number;
    postgres_sql?: string;
    snowflake_sql?: string;
    inflation_factor?: number;
    ticketed_accounts?: number;
    guard_result: {
      status: string;
      fan_out_detected: boolean;
      chasm_trap_detected?: boolean;
      left_join_trap_repaired?: boolean;
      fan_out_issues: JoinEdgeAnalysis[];
      join_graph?: JoinEdgeAnalysis[];
      partition_filter_present: boolean;
      warnings?: string[];
      explain_plan: string;
      error?: string | null;
    };
  } | null;
  semantic_plan?: {
    target_model: string;
    metric_name: string;
    metric_label: string;
    dimensions: string[];
    baseline_window: string;
    current_window: string;
    extra_filter?: string | null;
  };
  trace?: TraceStep[];
}

export interface SqlPreset {
  id: string;
  title: string;
  badge: string;
  description: string;
  sql: string;
}
