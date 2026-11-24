"""FastAPI server + SSE investigation stream + SQL AST Firewall Workbench for MetricPulse."""

from __future__ import annotations

import json
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import DB_PATH, MANIFEST_PATH, ROOT_DIR
from backend.engine.investigator import SCENARIOS, MetricInvestigator

app = FastAPI(title="MetricPulse RCA Platform", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SQL_WORKBENCH_PRESETS: list[dict[str, Any]] = [
    {
        "id": "fanout_1_to_n",
        "title": "1:N Support Ticket Revenue Fan-Out",
        "badge": "1:N Fan-Out Trap",
        "description": "Joins order-grain fct_revenue to ticket-grain stg_support_tickets on account_id, inflating revenue 3.4x.",
        "sql": """SELECT
    SUM(r.net_revenue_usd) AS total_net_revenue,
    COUNT(DISTINCT r.account_id) AS ticketed_accounts
FROM main_marts.fct_revenue r
JOIN main_staging.stg_support_tickets t
    ON r.account_id = t.account_id
WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'""",
    },
    {
        "id": "chasm_n_to_m",
        "title": "N:M Order Items × Support Tickets Chasm Trap",
        "badge": "N:M Chasm Trap",
        "description": "Joins fct_revenue simultaneously to stg_support_tickets AND stg_order_items, creating a multi-branch Cartesian product.",
        "sql": """SELECT
    SUM(r.net_revenue_usd) AS total_net_revenue,
    SUM(oi.quantity) AS total_units
FROM main_marts.fct_revenue r
JOIN main_staging.stg_support_tickets t
    ON r.account_id = t.account_id
JOIN main_staging.stg_order_items oi
    ON r.order_id = oi.order_id
WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND t.created_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'""",
    },
    {
        "id": "left_join_null_rejection",
        "title": "LEFT JOIN Null-Rejection WHERE Trap",
        "badge": "LEFT JOIN Trap",
        "description": "Places a right-table filter (t.priority = 'high') in the outer WHERE clause, silently turning LEFT JOIN into INNER JOIN.",
        "sql": """SELECT
    r.region,
    COUNT(DISTINCT r.order_id) AS orders
FROM main_marts.fct_revenue r
LEFT JOIN main_staging.stg_support_tickets t
    ON r.account_id = t.account_id
WHERE r.order_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND t.priority = 'high'
GROUP BY r.region""",
    },
    {
        "id": "unpartitioned_scan",
        "title": "Unpartitioned Full-Table Scan",
        "badge": "Partition Guard",
        "description": "Queries fct_checkout_funnel without filtering on its required partition column (event_date).",
        "sql": """SELECT region, AVG(converted) AS conv_rate
FROM main_marts.fct_checkout_funnel
GROUP BY region""",
    },
    {
        "id": "ddl_mutation_attack",
        "title": "DDL / DML Mutation Injection",
        "badge": "Mutation Block",
        "description": "Attempts to execute a destructive DROP TABLE statement against the warehouse.",
        "sql": """DROP TABLE main_marts.fct_revenue""",
    },
]


def _investigator() -> MetricInvestigator:
    return MetricInvestigator(MANIFEST_PATH, DB_PATH)


class InvestigateRequest(BaseModel):
    question: str = ""
    scenario_id: str | None = None


class SqlInspectRequest(BaseModel):
    sql: str
    dialect: str = "duckdb"
    target_dialect: str = "postgres"
    strict_partition: bool = True
    execute: bool = True


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "duckdb_exists": DB_PATH.exists(),
        "manifest_exists": MANIFEST_PATH.exists(),
    }


@app.get("/api/anomalies")
def list_anomalies() -> dict[str, Any]:
    return {"anomalies": SCENARIOS}


@app.get("/api/sql/presets")
def list_sql_presets() -> dict[str, Any]:
    return {"presets": SQL_WORKBENCH_PRESETS}


@app.post("/api/investigate")
def investigate(req: InvestigateRequest) -> dict[str, Any]:
    try:
        return _investigator().investigate(question=req.question, scenario_id=req.scenario_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/investigate/stream")
def investigate_stream(
    question: str = Query(default=""),
    scenario_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Server-Sent Events stream emitting stage-by-stage RCA progress and trace telemetry."""

    def event_generator():
        events: list[tuple[str, dict[str, Any]]] = []

        def emit(stage: str, payload: dict[str, Any]) -> None:
            events.append((stage, payload))

        inv = _investigator()
        inv.investigate(question=question, scenario_id=scenario_id, emit=emit)
        for stage, payload in events:
            yield f"event: {stage}\ndata: {json.dumps(payload, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/sql/inspect")
def inspect_sql(req: SqlInspectRequest) -> dict[str, Any]:
    inv = _investigator()
    guard_res = inv.guard.inspect_and_rewrite(
        req.sql,
        dialect=req.dialect,
        strict_partition=req.strict_partition,
    )
    transpiled: dict[str, str] = {}
    if guard_res.allowed and guard_res.safe_sql:
        for target in ("postgres", "snowflake", "bigquery"):
            try:
                transpiled[target] = inv.guard.transpile_sql(guard_res.safe_sql, req.dialect, target)
            except Exception:
                transpiled[target] = ""

    naive_rows: list[dict[str, Any]] = []
    safe_rows: list[dict[str, Any]] = []
    if req.execute and guard_res.allowed and guard_res.safe_sql:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            cur = con.execute(guard_res.safe_sql)
            cols = [d[0] for d in cur.description]
            safe_rows = [dict(zip(cols, r)) for r in cur.fetchall()[:25]]
            if guard_res.fan_out_detected or guard_res.left_join_trap_repaired:
                cur_n = con.execute(req.sql)
                cols_n = [d[0] for d in cur_n.description]
                naive_rows = [dict(zip(cols_n, r)) for r in cur_n.fetchall()[:25]]
        except Exception:
            pass
        finally:
            con.close()

    return {
        "guard_result": guard_res.to_dict(),
        "transpiled_sql": transpiled.get(req.target_dialect, ""),
        "transpiled_dialects": transpiled,
        "target_dialect": req.target_dialect,
        "rows": safe_rows,
        "naive_rows": naive_rows,
    }


@app.get("/api/lineage/{model_name}")
def get_lineage(model_name: str) -> dict[str, Any]:
    inv = _investigator()
    triage = inv.triage_gate.run_triage(model_name)
    dag = inv.graph.get_lineage_dag(model_name, triage.node_health)
    return {"triage": triage.to_dict(), "lineage": dag}


# Serve built frontend if present
frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
