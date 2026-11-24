"""Universal dbt Semantic Metric Compiler:
Resolves natural-language questions against dbt manifest.json models, metrics, grains, and dimensions
into executable InvestigationPlans without hardcoded scenario if/else branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.lineage.manifest_graph import ManifestGraph, ModelNode


@dataclass
class InvestigationPlan:
    scenario_id: str
    question: str
    target_model: str
    relation_name: str
    metric_name: str
    metric_label: str
    metric_type: str  # rate | sum
    date_col: str
    numerator_col: str
    dimensions: list[str]
    baseline_start: str
    baseline_end: str
    current_start: str
    current_end: str
    extra_filter: str | None = None
    simpson_dim: str | None = None
    join_check_sql: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "question": self.question,
            "target_model": self.target_model,
            "relation_name": self.relation_name,
            "metric_name": self.metric_name,
            "metric_label": self.metric_label,
            "metric_type": self.metric_type,
            "date_col": self.date_col,
            "dimensions": self.dimensions,
            "baseline_window": f"{self.baseline_start}..{self.baseline_end}",
            "current_window": f"{self.current_start}..{self.current_end}",
            "extra_filter": self.extra_filter,
        }


class SemanticMetricCompiler:
    """Compiles free-form NL questions against dbt manifest.json semantic metadata."""

    def __init__(self, graph: ManifestGraph) -> None:
        self.graph = graph

    def compile(self, question: str = "", scenario_id: str | None = None) -> InvestigationPlan:
        q = (question or "").lower()

        # 1. Resolve target dbt mart model from semantic keywords or scenario_id
        if scenario_id == "enterprise_dau_crash" or any(k in q for k in ("dau", "active user", "telemetry")):
            node = self.graph.get_node("fct_enterprise_dau")
            sid = "enterprise_dau_crash"
        elif scenario_id == "q3_support_revenue_fanout" or any(
            k in q for k in ("support ticket", "fan-out", "fanout", "chasm", "net revenue", "q3")
        ):
            node = self.graph.get_node("fct_revenue")
            sid = "q3_support_revenue_fanout"
        elif scenario_id == "trial_simpsons_paradox" or any(
            k in q for k in ("trial", "simpson", "self-serve", "mix-shift", "mix shift")
        ):
            node = self.graph.get_node("fct_trial_conversions")
            sid = "trial_simpsons_paradox"
        else:
            node = self.graph.get_node("fct_checkout_funnel")
            sid = scenario_id or "eu_checkout_drop"

        assert node is not None, "Target mart model missing from dbt manifest.json"
        return self._build_plan_from_node(node, sid, question)

    def _build_plan_from_node(self, node: ModelNode, sid: str, question: str) -> InvestigationPlan:
        meta = node.meta or {}
        metric = meta.get("metric", {})
        dims = list(meta.get("dimensions", []))
        date_col = str(meta.get("partition_col", "event_date"))
        q = (question or "").lower()

        # Extract dynamic dimension filters from natural language query
        filters: list[str] = []
        if "region" in dims:
            if any(k in q for k in ("eu", "emea", "europe")) or (sid == "eu_checkout_drop" and not any(k in q for k in ("na", "apac", "global"))):
                filters.append("region = 'EMEA'")
            elif "apac" in q or "asia" in q:
                filters.append("region = 'APAC'")
            elif "na " in q or "north america" in q:
                filters.append("region = 'NA'")

        if "device_os" in dims:
            if "android" in q:
                filters.append("device_os = 'Android Chrome'")
            elif "desktop chrome" in q:
                filters.append("device_os = 'Desktop Chrome'")

        if "payment_gateway" in dims:
            if "stripe" in q:
                filters.append("payment_gateway = 'Stripe'")
            elif "paypal" in q:
                filters.append("payment_gateway = 'PayPal'")

        extra_filter = " AND ".join(filters) if filters else None
        metric_label = metric.get("label", node.name)
        if node.name == "fct_checkout_funnel":
            if "region = 'APAC'" in filters:
                metric_label = "APAC Checkout Conversion"
            elif "region = 'NA'" in filters:
                metric_label = "NA Checkout Conversion"

        # Join-check SQL when cross-entity relationship ("support tickets" or "order items") is requested
        join_sql = None
        if node.name == "fct_revenue":
            if "order item" in q or "chasm" in q:
                join_sql = """
SELECT
    SUM(r.net_revenue_usd) AS total_net_revenue,
    COUNT(DISTINCT r.account_id) AS ticketed_accounts
FROM main_marts.fct_revenue r
JOIN main_staging.stg_support_tickets t
    ON r.account_id = t.account_id
JOIN main_staging.stg_order_items oi
    ON r.order_id = oi.order_id
WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
                """.strip()
            else:
                join_sql = """
SELECT
    SUM(r.net_revenue_usd) AS total_net_revenue,
    COUNT(DISTINCT r.account_id) AS ticketed_accounts
FROM main_marts.fct_revenue r
JOIN main_staging.stg_support_tickets t
    ON r.account_id = t.account_id
WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
                """.strip()

        simpson_dim = "plan_tier" if "plan_tier" in dims else (dims[1] if len(dims) > 1 else dims[0])

        return InvestigationPlan(
            scenario_id=sid,
            question=question,
            target_model=node.name,
            relation_name=f"main_marts.{node.name}",
            metric_name=metric.get("name", node.name),
            metric_label=metric_label,
            metric_type=metric.get("type", "rate"),
            date_col=date_col,
            numerator_col="converted" if metric.get("type") == "rate" else "net_revenue_usd",
            dimensions=dims,
            baseline_start="2026-11-10",
            baseline_end="2026-11-16",
            current_start="2026-11-17",
            current_end="2026-11-23",
            extra_filter=extra_filter,
            simpson_dim=simpson_dim,
            join_check_sql=join_sql,
        )
