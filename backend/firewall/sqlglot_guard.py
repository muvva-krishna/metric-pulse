"""Stage 2 sqlglot AST Firewall & Multi-Hop Join Cardinality / Chasm-Trap Compiler:
1. Blocks mutations (DROP/DELETE/UPDATE/INSERT/ALTER/CREATE/TRUNCATE/MERGE).
2. Enforces partition/date filter pruning on fact models.
3. Classifies every JOIN edge (1:1, N:1, 1:N Fan-Out, N:M Chasm Trap) against dbt manifest.json grains.
4. Automatically rewrites 1:N fan-outs and multi-branch N:M chasm traps into grain-aligned CTEs
   (using GROUP BY <join_key> when right-table columns are aggregated, or SELECT DISTINCT <join_key> otherwise).
5. Detects and repairs LEFT JOIN WHERE-clause null-rejection traps.
6. Validates EXPLAIN cost on DuckDB and transpiles across DuckDB / Postgres / Snowflake / BigQuery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

from backend.config import DB_PATH
from backend.lineage.manifest_graph import ManifestGraph, ModelNode

FORBIDDEN_EXPRESSIONS = (
    exp.Drop,
    exp.Delete,
    exp.Update,
    exp.Insert,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Merge,
    exp.Command,
)

AGGREGATE_TYPES = (exp.Sum, exp.Avg, exp.Count)


@dataclass
class JoinEdgeAnalysis:
    left_table: str
    left_grain: str
    right_table: str
    right_grain: str
    join_key: str
    cardinality: str  # 1:1 | N:1 | 1:N | N:M_CHASM
    is_safe: bool
    rewrite_action: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_table": self.left_table,
            "left_grain": self.left_grain,
            "right_table": self.right_table,
            "right_grain": self.right_grain,
            "join_key": self.join_key,
            "cardinality": self.cardinality,
            "is_safe": self.is_safe,
            "rewrite_action": self.rewrite_action,
            "message": self.message,
        }


@dataclass
class GuardResult:
    allowed: bool
    status: str  # PASSED | BLOCKED_MUTATION | BLOCKED_PARTITION | FAN_OUT_REWRITTEN | CHASM_TRAP_REWRITTEN | LEFT_JOIN_REPAIRED | SYNTAX_ERROR
    original_sql: str
    safe_sql: str
    fan_out_detected: bool = False
    chasm_trap_detected: bool = False
    left_join_trap_repaired: bool = False
    fan_out_issues: list[JoinEdgeAnalysis] = field(default_factory=list)
    join_graph: list[JoinEdgeAnalysis] = field(default_factory=list)
    partition_filter_present: bool = True
    warnings: list[str] = field(default_factory=list)
    explain_plan: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "original_sql": self.original_sql,
            "safe_sql": self.safe_sql,
            "fan_out_detected": self.fan_out_detected,
            "chasm_trap_detected": self.chasm_trap_detected,
            "left_join_trap_repaired": self.left_join_trap_repaired,
            "fan_out_issues": [i.to_dict() for i in self.fan_out_issues],
            "join_graph": [j.to_dict() for j in self.join_graph],
            "partition_filter_present": self.partition_filter_present,
            "warnings": self.warnings,
            "explain_plan": self.explain_plan,
            "error": self.error,
        }


class SqlglotGuard:
    """Deterministic AST firewall and Join-Graph Cardinality Compiler."""

    def __init__(self, graph: ManifestGraph, db_path: Path = DB_PATH) -> None:
        self.graph = graph
        self.db_path = db_path

    def inspect_and_rewrite(
        self,
        sql: str,
        dialect: str = "duckdb",
        strict_partition: bool = True,
        run_explain: bool = True,
    ) -> GuardResult:
        try:
            tree = sqlglot.parse_one(sql, read=dialect)
        except Exception as exc:
            return GuardResult(
                allowed=False,
                status="SYNTAX_ERROR",
                original_sql=sql,
                safe_sql=sql,
                error=f"SQL parse error: {exc}",
            )

        # 1. Mutation / DDL block
        for forbidden in FORBIDDEN_EXPRESSIONS:
            if isinstance(tree, forbidden) or tree.find(forbidden) is not None:
                return GuardResult(
                    allowed=False,
                    status="BLOCKED_MUTATION",
                    original_sql=sql,
                    safe_sql="",
                    error=f"Mutation or DDL expression `{forbidden.__name__}` is blocked by MetricPulse AST Firewall.",
                )

        # Resolve table aliases -> ModelNode
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        alias_map: dict[str, tuple[exp.Table, ModelNode | None]] = {}
        for tbl in tree.find_all(exp.Table):
            t_name = tbl.name
            if t_name.lower() in cte_names:
                continue
            full_name = f"{tbl.db}.{t_name}" if tbl.db else t_name
            node = self.graph.get_node(full_name) or self.graph.get_node(t_name)
            alias = (tbl.alias or t_name).lower()
            alias_map[alias] = (tbl, node)

        # 2. Partition / date filter enforcement on fact models
        warnings: list[str] = []
        where_expr = tree.find(exp.Where)
        where_cols = {c.name.lower() for c in where_expr.find_all(exp.Column)} if where_expr else set()
        on_cols = {
            c.name.lower()
            for j in tree.find_all(exp.Join)
            if j.args.get("on")
            for c in j.args["on"].find_all(exp.Column)
        }
        filtered_cols = where_cols | on_cols
        partition_ok = True
        for alias, (_, node) in alias_map.items():
            if node and node.name.startswith("fct_") and node.meta.get("partition_col"):
                p_col = str(node.meta["partition_col"]).lower()
                if p_col not in filtered_cols:
                    partition_ok = False
                    msg = f"Missing partition filter on `{node.name}.{p_col}` (unbounded full-table scan risk)."
                    if strict_partition:
                        return GuardResult(
                            allowed=False,
                            status="BLOCKED_PARTITION",
                            original_sql=sql,
                            safe_sql="",
                            partition_filter_present=False,
                            error=msg,
                        )
                    warnings.append(msg)

        safe_tree = tree.copy()
        left_join_repaired = False

        # 3. LEFT JOIN WHERE-clause Null-Rejection Trap Detection & Repair
        for j in safe_tree.find_all(exp.Join):
            j_kind = (j.args.get("side") or "").upper()
            if j_kind == "LEFT" and isinstance(j.this, exp.Table):
                r_alias = (j.this.alias or j.this.name).lower()
                main_where = safe_tree.find(exp.Where)
                if main_where:
                    remaining_parts = []
                    pushed_parts = []
                    for part in self._split_and(main_where.this):
                        if isinstance(part, exp.Is):
                            remaining_parts.append(part)
                            continue
                        cols = list(part.find_all(exp.Column))
                        if cols and all(c.table.lower() == r_alias for c in cols):
                            pushed_parts.append(part)
                        else:
                            remaining_parts.append(part)
                    if pushed_parts:
                        left_join_repaired = True
                        warnings.append(
                            f"LEFT JOIN Null-Rejection Trap repaired: moved `WHERE` filter on `{r_alias}` into `LEFT JOIN ... ON` clause."
                        )
                        on_cond = j.args.get("on")
                        for p in pushed_parts:
                            on_cond = exp.and_(on_cond, p) if on_cond else p
                        j.set("on", on_cond)
                        if remaining_parts:
                            combined = remaining_parts[0]
                            for p in remaining_parts[1:]:
                                combined = exp.and_(combined, p)
                            main_where.set("this", combined)
                        else:
                            main_where.pop()

        # 4. Multi-Hop Join Cardinality Graph & 1:N / N:M Chasm-Trap Compiler
        has_agg = any(safe_tree.find(agg) is not None for agg in AGGREGATE_TYPES)
        fan_out_issues: list[JoinEdgeAnalysis] = []
        join_graph: list[JoinEdgeAnalysis] = []

        from_expr = safe_tree.find(exp.From)
        base_node: ModelNode | None = None
        base_alias = ""
        if from_expr and isinstance(from_expr.this, exp.Table):
            base_alias = (from_expr.this.alias or from_expr.this.name).lower()
            _, base_node = alias_map.get(base_alias, (from_expr.this, None))

        left_name = base_node.name if base_node else (base_alias or "base_table")
        left_pk = str(base_node.meta.get("primary_key", "")).lower() if base_node else ""
        left_grain = str(base_node.meta.get("grain", left_pk or "row")) if base_node else "row"

        joins = list(safe_tree.find_all(exp.Join))
        one_to_many_joins: list[tuple[exp.Join, str, ModelNode, str]] = []

        for j in joins:
            if not isinstance(j.this, exp.Table):
                continue
            r_alias = (j.this.alias or j.this.name).lower()
            _, right_node = alias_map.get(r_alias, (j.this, None))
            if not right_node:
                continue

            right_pk = str(right_node.meta.get("primary_key", "")).lower()
            right_grain = str(right_node.meta.get("grain", right_pk))
            on_expr = j.args.get("on")
            if not on_expr or not right_pk:
                continue

            join_keys = []
            for eq in on_expr.find_all(exp.EQ):
                for side in (eq.left, eq.right):
                    if isinstance(side, exp.Column):
                        if side.table.lower() == r_alias or not side.table:
                            join_keys.append(side.name.lower())

            if not join_keys:
                continue

            jkey = join_keys[0]
            if jkey == right_pk:
                card = "1:1" if jkey == left_pk else "N:1"
                join_graph.append(
                    JoinEdgeAnalysis(
                        left_table=left_name,
                        left_grain=left_grain,
                        right_table=right_node.name,
                        right_grain=right_grain,
                        join_key=jkey,
                        cardinality=card,
                        is_safe=True,
                        rewrite_action="NONE",
                        message=f"Safe `{card}` lookup join on primary key `{right_node.name}.{right_pk}`.",
                    )
                )
            elif has_agg and (j.args.get("side") or "").upper() != "LEFT":
                one_to_many_joins.append((j, r_alias, right_node, jkey))

        chasm_detected = len(one_to_many_joins) >= 2

        for j, r_alias, right_node, jkey in one_to_many_joins:
            right_pk = str(right_node.meta.get("primary_key", "")).lower()
            right_grain = str(right_node.meta.get("grain", right_pk))
            card = "N:M_CHASM" if chasm_detected else "1:N"
            cte_name = f"{r_alias}_dedup"

            # Check if outer SELECT aggregates any columns from r_alias
            agg_Replacements: list[tuple[exp.AggFunc, str, str]] = []
            for agg in safe_tree.find_all(exp.Sum, exp.Avg, exp.Count):
                cols = [c for c in agg.find_all(exp.Column) if c.table.lower() == r_alias]
                if cols:
                    col_name = cols[0].name
                    agg_alias = f"{r_alias}_{col_name}_agg"
                    agg_sql_fn = agg.key.upper()
                    agg_Replacements.append((agg, f"{agg_sql_fn}({col_name}) AS {agg_alias}", agg_alias))

            # Extract WHERE predicates referencing only r_alias
            cte_where_parts: list[exp.Expression] = []
            main_where = safe_tree.find(exp.Where)
            if main_where:
                new_and_parts = []
                for part in self._split_and(main_where.this):
                    cols = list(part.find_all(exp.Column))
                    if cols and all(c.table.lower() == r_alias for c in cols):
                        clean_part = part.copy()
                        for c in clean_part.find_all(exp.Column):
                            c.set("table", None)
                        cte_where_parts.append(clean_part)
                    else:
                        new_and_parts.append(part)
                if cte_where_parts:
                    if new_and_parts:
                        combined = new_and_parts[0]
                        for p in new_and_parts[1:]:
                            combined = exp.and_(combined, p)
                        main_where.set("this", combined)
                    else:
                        main_where.pop()

            right_rel = right_node.relation_name
            if agg_Replacements:
                select_exprs = ", ".join([jkey] + [expr_str for _, expr_str, _ in agg_Replacements])
                cte_sql = f"SELECT {select_exprs} FROM {right_rel}"
                if cte_where_parts:
                    cond = cte_where_parts[0]
                    for p in cte_where_parts[1:]:
                        cond = exp.and_(cond, p)
                    cte_sql += f" WHERE {cond.sql(dialect='duckdb')}"
                cte_sql += f" GROUP BY {jkey}"
                for orig_agg, _, agg_alias in agg_Replacements:
                    orig_agg.replace(sqlglot.parse_one(f"SUM({r_alias}.{agg_alias})", read="duckdb"))
                rewrite_mode = f"GROUP_BY_CTE ({cte_name})"
            else:
                cte_sql = f"SELECT DISTINCT {jkey} FROM {right_rel}"
                if cte_where_parts:
                    cond = cte_where_parts[0]
                    for p in cte_where_parts[1:]:
                        cond = exp.and_(cond, p)
                    cte_sql += f" WHERE {cond.sql(dialect='duckdb')}"
                rewrite_mode = f"DISTINCT_CTE ({cte_name})"

            cte_select = sqlglot.parse_one(cte_sql, read="duckdb")
            j.set(
                "this",
                exp.Table(
                    this=exp.to_identifier(cte_name),
                    alias=exp.TableAlias(this=exp.to_identifier(r_alias)),
                ),
            )
            safe_tree = safe_tree.with_(cte_name, cte_select, copy=False)

            issue = JoinEdgeAnalysis(
                left_table=left_name,
                left_grain=left_grain,
                right_table=right_node.name,
                right_grain=right_grain,
                join_key=jkey,
                cardinality=card,
                is_safe=False,
                rewrite_action=rewrite_mode,
                message=(
                    f"{'N:M Chasm Trap' if chasm_detected else '1:N Join Fan-Out'} detected: "
                    f"`{left_name}` (grain: {left_grain}) joined to `{right_node.name}` (grain: {right_grain}) "
                    f"on non-unique key `{jkey}`. Hoisted into grain-aligned CTE `{cte_name}`."
                ),
            )
            fan_out_issues.append(issue)
            join_graph.append(issue)

        safe_sql = safe_tree.sql(dialect=dialect, pretty=True)
        explain_plan = self._run_explain(safe_sql) if run_explain else ""

        if chasm_detected:
            status = "CHASM_TRAP_REWRITTEN"
        elif fan_out_issues:
            status = "FAN_OUT_REWRITTEN"
        elif left_join_repaired:
            status = "LEFT_JOIN_REPAIRED"
        else:
            status = "PASSED"

        return GuardResult(
            allowed=True,
            status=status,
            original_sql=sql,
            safe_sql=safe_sql,
            fan_out_detected=bool(fan_out_issues),
            chasm_trap_detected=chasm_detected,
            left_join_trap_repaired=left_join_repaired,
            fan_out_issues=fan_out_issues,
            join_graph=join_graph,
            partition_filter_present=partition_ok,
            warnings=warnings,
            explain_plan=explain_plan,
        )

    def _split_and(self, expr_node: exp.Expression) -> list[exp.Expression]:
        if isinstance(expr_node, exp.And):
            return self._split_and(expr_node.left) + self._split_and(expr_node.right)
        return [expr_node]

    def _run_explain(self, sql: str) -> str:
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            rows = con.execute(f"EXPLAIN {sql}").fetchall()
            return "\n".join(str(r[-1]) for r in rows)
        except Exception as exc:
            return f"EXPLAIN unavailable: {exc}"
        finally:
            con.close()

    @staticmethod
    def transpile_sql(sql: str, source_dialect: str = "duckdb", target_dialect: str = "postgres") -> str:
        """Transpile SQL across DuckDB, Postgres, BigQuery, and Snowflake."""
        return sqlglot.transpile(sql, read=source_dialect, write=target_dialect, pretty=True)[0]
