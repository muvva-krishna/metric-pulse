"""Stage 1 Triage Gate: walks dbt lineage upstream to detect staleness, volume drops, and NULL spikes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from backend.config import (
    DB_PATH,
    DEFAULT_FRESHNESS_SLA_HOURS,
    NULL_RATE_ABS_THRESHOLD,
    NULL_RATE_SPIKE_THRESHOLD,
    REF_NOW,
    ROW_VOLUME_Z_THRESHOLD,
)
from backend.lineage.manifest_graph import ManifestGraph, ModelNode


@dataclass
class NodeHealth:
    model_name: str
    status: str  # HEALTHY | WARNING | INCIDENT
    lag_hours: float | None = None
    freshness_sla_hours: float = DEFAULT_FRESHNESS_SLA_HOURS
    latest_date: str | None = None
    latest_row_count: int | None = None
    baseline_avg_rows: float | None = None
    volume_z_score: float | None = None
    null_spikes: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "status": self.status,
            "lag_hours": self.lag_hours,
            "freshness_sla_hours": self.freshness_sla_hours,
            "latest_date": self.latest_date,
            "latest_row_count": self.latest_row_count,
            "baseline_avg_rows": self.baseline_avg_rows,
            "volume_z_score": self.volume_z_score,
            "null_spikes": self.null_spikes,
            "reasons": self.reasons,
        }


@dataclass
class TriageResult:
    status: str  # HEALTHY | PIPELINE_INCIDENT
    target_model: str
    broken_nodes: list[NodeHealth]
    node_health: dict[str, dict[str, Any]]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target_model": self.target_model,
            "broken_nodes": [n.to_dict() for n in self.broken_nodes],
            "node_health": self.node_health,
            "summary": self.summary,
        }


class PipelineTriageGate:
    """Checks upstream dbt nodes for freshness, row-volume continuity, and NULL-rate spikes."""

    def __init__(
        self,
        graph: ManifestGraph,
        db_path: Path = DB_PATH,
        ref_now: datetime = REF_NOW,
    ) -> None:
        self.graph = graph
        self.db_path = db_path
        self.ref_now = ref_now

    def run_triage(self, target_model: str) -> TriageResult:
        upstream = self.graph.get_upstream_nodes(target_model, include_self=True)
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            node_health: dict[str, dict[str, Any]] = {}
            broken: list[NodeHealth] = []

            for node in upstream:
                if node.resource_type == "source":
                    continue
                health = self._check_node(con, node)
                node_health[node.name] = health.to_dict()
                if health.status == "INCIDENT":
                    broken.append(health)

            # Propagate incident status to source nodes feeding broken staging models
            for node in upstream:
                if node.resource_type == "source":
                    node_health[node.name] = {
                        "model_name": node.name,
                        "status": "HEALTHY",
                        "reasons": [],
                    }

            if broken:
                names = ", ".join(b.model_name for b in broken)
                details = "; ".join(r for b in broken for r in b.reasons)
                return TriageResult(
                    status="PIPELINE_INCIDENT",
                    target_model=target_model,
                    broken_nodes=broken,
                    node_health=node_health,
                    summary=f"Upstream data pipeline outage detected in [{names}]: {details}",
                )

            return TriageResult(
                status="HEALTHY",
                target_model=target_model,
                broken_nodes=[],
                node_health=node_health,
                summary=f"All upstream dbt models for {target_model} passed freshness, volume, and NULL checks.",
            )
        finally:
            con.close()

    def _check_node(self, con: duckdb.DuckDBPyConnection, node: ModelNode) -> NodeHealth:
        meta = node.meta or {}
        sla_hours = float(meta.get("freshness_sla_hours", DEFAULT_FRESHNESS_SLA_HOURS))
        ingested_col = meta.get("ingested_col")
        date_col = meta.get("date_col") or meta.get("partition_col")
        non_null_cols = meta.get("critical_non_null_cols", [])
        relation = node.relation_name

        health = NodeHealth(
            model_name=node.name,
            status="HEALTHY",
            freshness_sla_hours=sla_hours,
        )

        # 1. Freshness check
        if ingested_col:
            row = con.execute(f"SELECT MAX({ingested_col}) FROM {relation}").fetchone()
            max_ts = row[0] if row else None
            if max_ts is not None:
                if isinstance(max_ts, str):
                    max_ts = datetime.fromisoformat(max_ts)
                lag = round((self.ref_now - max_ts).total_seconds() / 3600.0, 2)
                health.lag_hours = lag
                if lag > sla_hours:
                    health.status = "INCIDENT"
                    health.reasons.append(
                        f"Freshness SLA breached: last ingested {lag:.1f}h ago (SLA: {sla_hours:.0f}h)"
                    )

        # 2. Row-volume z-score (for tables with a date column)
        if date_col and node.name.startswith("stg_"):
            daily = con.execute(
                f"""
                SELECT CAST({date_col} AS DATE) AS d, COUNT(*) AS cnt
                FROM {relation}
                GROUP BY 1
                ORDER BY 1 DESC
                LIMIT 31
                """
            ).fetchall()
            if len(daily) >= 7:
                latest_d, latest_cnt = daily[0]
                health.latest_date = str(latest_d)
                health.latest_row_count = int(latest_cnt)
                hist = [float(r[1]) for r in daily[1:]]
                mean = sum(hist) / len(hist)
                var = sum((x - mean) ** 2 for x in hist) / len(hist)
                std = var ** 0.5
                health.baseline_avg_rows = round(mean, 1)
                if std > 0:
                    z = (latest_cnt - mean) / std
                    health.volume_z_score = round(z, 2)
                    if z < ROW_VOLUME_Z_THRESHOLD:
                        health.status = "INCIDENT"
                        health.reasons.append(
                            f"Row volume collapsed on {latest_d}: {latest_cnt} rows vs {mean:.0f} avg (z={z:.2f})"
                        )

            # 3. NULL-rate spike detection on critical columns
            if non_null_cols and health.latest_date:
                for col in non_null_cols:
                    res = con.execute(
                        f"""
                        SELECT
                            AVG(CASE WHEN CAST({date_col} AS DATE) = DATE '{health.latest_date}'
                                THEN CASE WHEN {col} IS NULL THEN 1.0 ELSE 0.0 END END) AS latest_null,
                            AVG(CASE WHEN CAST({date_col} AS DATE) < DATE '{health.latest_date}'
                                     AND CAST({date_col} AS DATE) >= DATE '{health.latest_date}' - INTERVAL 30 DAY
                                THEN CASE WHEN {col} IS NULL THEN 1.0 ELSE 0.0 END END) AS base_null
                        FROM {relation}
                        """
                    ).fetchone()
                    latest_null = float(res[0] or 0.0)
                    base_null = float(res[1] or 0.0)
                    delta = latest_null - base_null
                    if latest_null >= NULL_RATE_ABS_THRESHOLD or delta >= NULL_RATE_SPIKE_THRESHOLD:
                        health.status = "INCIDENT"
                        spike_info = {
                            "column": col,
                            "latest_null_pct": round(latest_null * 100, 1),
                            "baseline_null_pct": round(base_null * 100, 1),
                        }
                        health.null_spikes.append(spike_info)
                        health.reasons.append(
                            f"NULL spike in `{col}`: {latest_null * 100:.1f}% NULLs (baseline {base_null * 100:.1f}%)"
                        )

        return health
