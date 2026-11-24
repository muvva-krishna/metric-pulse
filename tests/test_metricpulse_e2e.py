"""End-to-end verification of MetricPulse Phase 2 FDE Architecture:
- sqlglot AST Firewall (mutations, partition guard, 1:N fan-out, N:M Chasm Trap, LEFT JOIN null-rejection repair, multi-dialect transpilation)
- Universal dbt Semantic Metric Compiler (ad-hoc regional/device queries)
- Benjamini-Hochberg False Discovery Rate (FDR) statistical attribution
- Automated dbt schema.yml contract patch & DLQ MERGE backfill synthesis
- All 4 seeded enterprise mysteries + FastAPI endpoints
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config import DB_PATH, MANIFEST_PATH
from backend.engine.investigator import MetricInvestigator
from backend.firewall.sqlglot_guard import SqlglotGuard
from backend.lineage.manifest_graph import ManifestGraph
from backend.main import app


def test_sqlglot_firewall_blocks_mutations() -> None:
    graph = ManifestGraph(MANIFEST_PATH)
    guard = SqlglotGuard(graph, DB_PATH)

    for bad_sql in [
        "DROP TABLE main_marts.fct_revenue",
        "DELETE FROM main_marts.fct_revenue WHERE order_date = DATE '2026-09-01'",
        "UPDATE main_marts.fct_revenue SET net_revenue_usd = 0 WHERE order_date = DATE '2026-09-01'",
    ]:
        res = guard.inspect_and_rewrite(bad_sql)
        assert not res.allowed
        assert res.status == "BLOCKED_MUTATION"


def test_sqlglot_firewall_enforces_partition_filter() -> None:
    graph = ManifestGraph(MANIFEST_PATH)
    guard = SqlglotGuard(graph, DB_PATH)

    res = guard.inspect_and_rewrite("SELECT SUM(net_revenue_usd) FROM main_marts.fct_revenue", strict_partition=True)
    assert not res.allowed
    assert res.status == "BLOCKED_PARTITION"


def test_sqlglot_firewall_rewrites_1_to_n_fanout() -> None:
    graph = ManifestGraph(MANIFEST_PATH)
    guard = SqlglotGuard(graph, DB_PATH)

    naive_sql = """
    SELECT SUM(r.net_revenue_usd) AS rev
    FROM main_marts.fct_revenue r
    JOIN main_staging.stg_support_tickets t ON r.account_id = t.account_id
    WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
      AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
    """
    res = guard.inspect_and_rewrite(naive_sql, strict_partition=True)
    assert res.allowed
    assert res.status == "FAN_OUT_REWRITTEN"
    assert res.fan_out_detected is True
    assert "t_dedup" in res.safe_sql
    assert "SELECT DISTINCT" in res.safe_sql.upper()
    assert "account_id" in res.safe_sql.lower()

    pg_sql = guard.transpile_sql(res.safe_sql, "duckdb", "postgres")
    assert "WITH t_dedup" in pg_sql


def test_sqlglot_firewall_rewrites_n_to_m_chasm_trap() -> None:
    graph = ManifestGraph(MANIFEST_PATH)
    guard = SqlglotGuard(graph, DB_PATH)

    chasm_sql = """
    SELECT
        SUM(r.net_revenue_usd) AS total_net_revenue,
        SUM(oi.quantity) AS total_units
    FROM main_marts.fct_revenue r
    JOIN main_staging.stg_support_tickets t ON r.account_id = t.account_id
    JOIN main_staging.stg_order_items oi ON r.order_id = oi.order_id
    WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
      AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
    """
    res = guard.inspect_and_rewrite(chasm_sql, strict_partition=True)
    assert res.allowed
    assert res.status == "CHASM_TRAP_REWRITTEN"
    assert res.chasm_trap_detected is True
    assert "t_dedup" in res.safe_sql
    assert "oi_dedup" in res.safe_sql
    assert all(edge.cardinality == "N:M_CHASM" for edge in res.fan_out_issues)


def test_sqlglot_firewall_repairs_left_join_null_rejection_trap() -> None:
    graph = ManifestGraph(MANIFEST_PATH)
    guard = SqlglotGuard(graph, DB_PATH)

    left_trap_sql = """
    SELECT r.region, COUNT(DISTINCT r.order_id) AS orders
    FROM main_marts.fct_revenue r
    LEFT JOIN main_staging.stg_support_tickets t ON r.account_id = t.account_id
    WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
      AND t.priority = 'high'
    GROUP BY r.region
    """
    res = guard.inspect_and_rewrite(left_trap_sql, strict_partition=True)
    assert res.allowed
    assert res.left_join_trap_repaired is True
    assert any("LEFT JOIN Null-Rejection Trap repaired" in w for w in res.warnings)


def test_mystery_1_eu_checkout_bug_and_bh_fdr() -> None:
    inv = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    brief = inv.investigate(question="Why did EU Checkout Conversion drop 19% this week?")

    assert brief["scenario_id"] == "eu_checkout_drop"
    assert brief["verdict_type"] == "LOCALIZED_PRODUCT_BUG"
    assert brief["triage"]["status"] == "HEALTHY"
    assert len(brief["trace"]) >= 3
    ov = brief["attribution"]["overall"]
    assert ov["significant_cohorts"] >= 1
    assert ov["noise_suppressed_cohorts"] >= 1

    top = brief["attribution"]["top_cohorts"][0]
    assert "EMEA" in top["segment"]
    assert "iOS Safari" in top["segment"]
    assert "Adyen_3DS" in top["segment"]
    assert "v2.14" in top["segment"]
    assert top["is_significant"] is True
    assert top["q_value"] <= 0.05
    assert top["contribution_pct"] >= 70.0


def test_mystery_2_enterprise_dau_pipeline_incident_and_remediation() -> None:
    inv = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    brief = inv.investigate(question="Why did Enterprise DAU crash 42% yesterday?")

    assert brief["scenario_id"] == "enterprise_dau_crash"
    assert brief["verdict_type"] == "PIPELINE_INCIDENT"
    assert brief["triage"]["status"] == "PIPELINE_INCIDENT"
    broken = brief["triage"]["broken_nodes"]
    assert any(n["model_name"] == "stg_telemetry_eu" for n in broken)

    rem = brief["remediation"]
    assert rem is not None
    assert rem["target_model"] == "stg_telemetry_eu"
    assert "not_null" in rem["dbt_schema_patch_yaml"]
    assert "MERGE INTO raw.telemetry_eu" in rem["backfill_sql"]


def test_mystery_3_q3_revenue_fanout_trap() -> None:
    inv = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    brief = inv.investigate(question="What is total Net Revenue for accounts with support tickets in Q3?")

    assert brief["scenario_id"] == "q3_support_revenue_fanout"
    assert brief["verdict_type"] == "FAN_OUT_GUARDED"
    proof = brief["sql_proof"]
    assert proof["safe_result"] == 418000.0
    assert proof["naive_result"] > 1_400_000.0
    assert proof["inflation_factor"] >= 3.3


def test_mystery_4_simpsons_paradox() -> None:
    inv = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    brief = inv.investigate(
        question="Why did overall trial-to-paid conversion fall while both Self-Serve and Enterprise rose?"
    )

    assert brief["scenario_id"] == "trial_simpsons_paradox"
    assert brief["verdict_type"] == "SIMPSONS_PARADOX"
    kitagawa = brief["attribution"]["kitagawa"]
    assert kitagawa["simpsons_paradox"] is True
    assert kitagawa["total_change"] < 0
    assert kitagawa["within_segment_effect"] > 0
    assert kitagawa["mix_shift_effect"] < 0


def test_universal_semantic_compiler_adhoc_query() -> None:
    inv = MetricInvestigator(MANIFEST_PATH, DB_PATH)
    brief = inv.investigate(question="Why did APAC Android checkout conversion move this week?")
    assert brief["target_model"] == "fct_checkout_funnel"
    assert brief["semantic_plan"]["extra_filter"] == "region = 'APAC' AND device_os = 'Android Chrome'"
    assert brief["attribution"]["overall"]["current_volume"] > 0


def test_fastapi_endpoints_and_workbench() -> None:
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert len(client.get("/api/anomalies").json()["anomalies"]) == 4
    presets = client.get("/api/sql/presets").json()["presets"]
    assert len(presets) == 5

    # Test N:M Chasm Trap preset through /api/sql/inspect
    chasm_preset = next(p for p in presets if p["id"] == "chasm_n_to_m")
    insp = client.post("/api/sql/inspect", json={"sql": chasm_preset["sql"], "execute": True}).json()
    assert insp["guard_result"]["chasm_trap_detected"] is True
    assert round(insp["rows"][0]["total_net_revenue"], 2) == 418000.0
    assert "snowflake" in insp["transpiled_dialects"]
