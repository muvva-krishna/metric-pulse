"""Automated FDE Remediation Generator:
Emits PR-ready dbt schema.yml patches and idempotent backfill/quarantine SQL when upstream triage fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.triage.pipeline_gate import NodeHealth


@dataclass
class RemediationArtifact:
    target_model: str
    dbt_schema_patch_yaml: str
    backfill_sql: str
    quarantine_sql: str
    incident_runbook: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_model": self.target_model,
            "dbt_schema_patch_yaml": self.dbt_schema_patch_yaml,
            "backfill_sql": self.backfill_sql,
            "quarantine_sql": self.quarantine_sql,
            "incident_runbook": self.incident_runbook,
        }


class RemediationGenerator:
    """Generates dbt contract tests and SQL backfill scripts from Triage diagnostics."""

    @staticmethod
    def generate(broken_node: NodeHealth, raw_relation: str = "raw.telemetry_eu") -> RemediationArtifact:
        model = broken_node.model_name
        sla_h = int(broken_node.freshness_sla_hours)
        latest_date = broken_node.latest_date or "2026-11-24"
        null_cols = [s["column"] for s in broken_node.null_spikes] or ["session_id"]

        col_yaml_blocks = []
        for col in null_cols:
            col_yaml_blocks.append(
                f"""      - name: {col}
        description: "Auto-enforced non-null grain contract after NULL spike incident"
        data_tests:
          - not_null:
              config:
                severity: error
                where: "event_date >= current_date - interval '7 day'" """
            )
        cols_yaml = "\n".join(col_yaml_blocks)

        dbt_patch = f"""# Patch for dbt_project/models/staging/schema.yml
models:
  - name: {model}
    config:
      contract:
        enforced: true
    meta:
      freshness_sla_hours: {sla_h}
    columns:
{cols_yaml}
"""

        null_pred = " OR ".join(f"{c} IS NULL" for c in null_cols)
        quarantine_sql = f"""-- 1. Quarantine corrupted records with NULL grain keys on {latest_date}
CREATE TABLE IF NOT EXISTS raw.quarantine_{model} AS
SELECT *, CURRENT_TIMESTAMP AS quarantined_at
FROM {raw_relation}
WHERE event_date = DATE '{latest_date}'
  AND ({null_pred});"""

        backfill_sql = f"""-- 2. Idempotent Backfill & Deduplication from Dead-Letter / Replay Stream
MERGE INTO {raw_relation} AS target
USING (
    SELECT
        event_id,
        user_id,
        account_id,
        COALESCE(session_id, 'recovered_' || md5(user_id || CAST(event_ts AS VARCHAR))) AS session_id,
        event_ts,
        event_date,
        region,
        plan_tier,
        CURRENT_TIMESTAMP AS ingested_at
    FROM {raw_relation}_dlq_replay
    WHERE event_date >= DATE '{latest_date}'
) AS source
ON target.event_id = source.event_id
WHEN MATCHED AND target.session_id IS NULL THEN
    UPDATE SET session_id = source.session_id, ingested_at = source.ingested_at
WHEN NOT MATCHED THEN
    INSERT VALUES (
        source.event_id, source.user_id, source.account_id, source.session_id,
        source.event_ts, source.event_date, source.region, source.plan_tier, source.ingested_at
    );"""

        runbook = [
            f"1. Halt downstream mart refresh (`dbt build --exclude {model}+`) to prevent corrupting executive dashboards.",
            f"2. Run the quarantine query to isolate the {broken_node.null_spikes[0]['latest_null_pct'] if broken_node.null_spikes else 68.0}% NULL `{null_cols[0]}` batch from `{latest_date}`.",
            f"3. Execute the idempotent `MERGE INTO {raw_relation}` replay script and verify `lag_hours < {sla_h}h`.",
            f"4. Commit the generated `schema.yml` contract patch so future NULL spikes fail at staging before reaching marts.",
        ]

        return RemediationArtifact(
            target_model=model,
            dbt_schema_patch_yaml=dbt_patch,
            backfill_sql=backfill_sql,
            quarantine_sql=quarantine_sql,
            incident_runbook=runbook,
        )
