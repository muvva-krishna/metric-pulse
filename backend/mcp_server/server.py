"""MetricPulse MCP Server aligned with dbt-labs/dbt-mcp conventions.

Exposes:
- get_metric_lineage(model_name)
- inspect_model_grain(model_name)
- run_guarded_sql(sql)
- investigate_metric(question)
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

from backend.config import DB_PATH, MANIFEST_PATH
from backend.engine.investigator import MetricInvestigator
from backend.firewall.sqlglot_guard import SqlglotGuard
from backend.lineage.manifest_graph import ManifestGraph

mcp = FastMCP("metricpulse-dbt-mcp")

_graph: ManifestGraph | None = None
_guard: SqlglotGuard | None = None
_investigator: MetricInvestigator | None = None


def _get_graph() -> ManifestGraph:
    global _graph
    if _graph is None:
        _graph = ManifestGraph(MANIFEST_PATH)
    return _graph


def _get_guard() -> SqlglotGuard:
    global _guard
    if _guard is None:
        _guard = SqlglotGuard(_get_graph(), DB_PATH)
    return _guard


def _get_investigator() -> MetricInvestigator:
    global _investigator
    if _investigator is None:
        _investigator = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    return _investigator


@mcp.tool()
def get_metric_lineage(model_name: str) -> str:
    """Return upstream dbt lineage DAG (nodes & edges) for a mart or staging model."""
    dag = _get_graph().get_lineage_dag(model_name)
    return json.dumps(dag, indent=2)


@mcp.tool()
def inspect_model_grain(model_name: str) -> str:
    """Inspect a dbt model's declared grain, primary_key, partition_col, and metric metadata."""
    node = _get_graph().get_node(model_name)
    if not node:
        return json.dumps({"error": f"Model '{model_name}' not found in manifest.json"})
    return json.dumps(
        {
            "name": node.name,
            "relation_name": node.relation_name,
            "description": node.description,
            "meta": node.meta,
        },
        indent=2,
    )


@mcp.tool()
def run_guarded_sql(sql: str) -> str:
    """Validate SQL through the sqlglot AST firewall (mutation, partition, 1:N fan-out) and execute on DuckDB."""
    guard_res = _get_guard().inspect_and_rewrite(sql, strict_partition=True)
    if not guard_res.allowed:
        return json.dumps({"blocked": True, "guard_result": guard_res.to_dict()}, indent=2)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        cur = con.execute(guard_res.safe_sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()[:100]]
    finally:
        con.close()

    return json.dumps(
        {
            "blocked": False,
            "guard_result": guard_res.to_dict(),
            "rows": rows,
        },
        indent=2,
        default=str,
    )


@mcp.tool()
def investigate_metric(question: str) -> str:
    """Run full 4-stage autonomous RCA (Triage -> Firewall -> Attribution -> Executive Brief)."""
    brief = _get_investigator().investigate(question=question)
    return json.dumps(brief, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
