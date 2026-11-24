"""Stage 3 Dimensional Hypothesis Tree & Statistical Attribution Math:
- Batched GROUPING SETS queries across valid dimensional hierarchies
- Contribution-to-Change (Delta Segment / Delta Total)
- Two-Proportion Z-Test + 95% Confidence Intervals + Benjamini-Hochberg False Discovery Rate (FDR) control
- Kitagawa-Oaxaca mix-shift decomposition for Simpson's Paradox detection
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from backend.config import DB_PATH
from backend.firewall.sqlglot_guard import GuardResult, SqlglotGuard


def _two_proportion_z_test(x0: int, n0: int, x1: int, n1: int) -> tuple[float, float, tuple[float, float]]:
    """Compute z-statistic, two-sided p-value, and 95% CI on (r1 - r0)."""
    if n0 <= 0 or n1 <= 0:
        return 0.0, 1.0, (0.0, 0.0)
    r0 = x0 / n0
    r1 = x1 / n1
    diff = r1 - r0
    p_pool = (x0 + x1) / (n0 + n1)
    se_pool = math.sqrt(max(p_pool * (1.0 - p_pool) * (1.0 / n0 + 1.0 / n1), 1e-12))
    z = diff / se_pool
    p_val = math.erfc(abs(z) / math.sqrt(2.0))
    se_unpooled = math.sqrt(max(r0 * (1.0 - r0) / n0 + r1 * (1.0 - r1) / n1, 1e-12))
    ci_low = diff - 1.96 * se_unpooled
    ci_high = diff + 1.96 * se_unpooled
    return z, p_val, (ci_low, ci_high)


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Compute Benjamini-Hochberg FDR-adjusted q-values."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    q_vals = [1.0] * m
    running_min = 1.0
    for rank_rev in range(m - 1, -1, -1):
        orig_idx, p = indexed[rank_rev]
        rank = rank_rev + 1
        q = min(running_min, (m / rank) * p)
        running_min = q
        q_vals[orig_idx] = min(1.0, max(0.0, q))
    return q_vals


@dataclass
class SegmentAttribution:
    dimension: str
    segment: str
    baseline_value: float
    current_value: float
    baseline_volume: int
    current_volume: int
    delta_pp_or_abs: float
    impact_score: float
    contribution_pct: float
    z_score: float = 0.0
    p_value: float = 1.0
    q_value: float = 1.0
    ci_95: tuple[float, float] = (0.0, 0.0)
    is_significant: bool = True
    significance_label: str = "SIGNIFICANT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "segment": self.segment,
            "baseline_value": round(self.baseline_value, 4),
            "current_value": round(self.current_value, 4),
            "baseline_volume": self.baseline_volume,
            "current_volume": self.current_volume,
            "delta": round(self.delta_pp_or_abs, 4),
            "impact_score": round(self.impact_score, 4),
            "contribution_pct": round(self.contribution_pct, 1),
            "z_score": round(self.z_score, 2),
            "p_value": round(self.p_value, 6),
            "q_value": round(self.q_value, 6),
            "ci_95": [round(self.ci_95[0], 4), round(self.ci_95[1], 4)],
            "is_significant": self.is_significant,
            "significance_label": self.significance_label,
        }


@dataclass
class KitagawaDecomposition:
    overall_baseline_rate: float
    overall_current_rate: float
    total_change: float
    within_segment_effect: float
    mix_shift_effect: float
    simpsons_paradox: bool
    segment_details: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_baseline_rate": round(self.overall_baseline_rate, 4),
            "overall_current_rate": round(self.overall_current_rate, 4),
            "total_change": round(self.total_change, 4),
            "within_segment_effect": round(self.within_segment_effect, 4),
            "mix_shift_effect": round(self.mix_shift_effect, 4),
            "simpsons_paradox": self.simpsons_paradox,
            "segment_details": self.segment_details,
            "explanation": self.explanation,
        }


class AttributionEngine:
    """Runs guarded GROUPING SETS attribution, BH-FDR hypothesis tests, and Kitagawa-Oaxaca decomposition."""

    def __init__(self, guard: SqlglotGuard, db_path: Path = DB_PATH) -> None:
        self.guard = guard
        self.db_path = db_path

    def analyze_rate_metric(
        self,
        relation_name: str,
        date_col: str,
        numerator_col: str,
        dimensions: list[str],
        baseline_start: str,
        baseline_end: str,
        current_start: str,
        current_end: str,
        extra_filter: str | None = None,
        simpson_dim: str | None = None,
    ) -> dict[str, Any]:
        """Run batched GROUPING SETS query through sqlglot firewall and compute BH-FDR attribution."""
        filter_clause = f"AND ({extra_filter})" if extra_filter else ""
        gs_items = ["()"] + [f"({d})" for d in dimensions]
        if len(dimensions) >= 2:
            gs_items.append(f"({', '.join(dimensions)})")
        grouping_sets_sql = ", ".join(gs_items)
        dim_select = ", ".join(dimensions)

        raw_sql = f"""
        SELECT
            {dim_select},
            SUM(CASE WHEN {date_col} BETWEEN DATE '{baseline_start}' AND DATE '{baseline_end}' THEN {numerator_col} ELSE 0 END) AS base_num,
            SUM(CASE WHEN {date_col} BETWEEN DATE '{baseline_start}' AND DATE '{baseline_end}' THEN 1 ELSE 0 END) AS base_den,
            SUM(CASE WHEN {date_col} BETWEEN DATE '{current_start}' AND DATE '{current_end}' THEN {numerator_col} ELSE 0 END) AS curr_num,
            SUM(CASE WHEN {date_col} BETWEEN DATE '{current_start}' AND DATE '{current_end}' THEN 1 ELSE 0 END) AS curr_den
        FROM {relation_name}
        WHERE {date_col} BETWEEN DATE '{baseline_start}' AND DATE '{current_end}'
        {filter_clause}
        GROUP BY GROUPING SETS ({grouping_sets_sql})
        """

        guard_res: GuardResult = self.guard.inspect_and_rewrite(raw_sql, strict_partition=True)
        if not guard_res.allowed:
            raise ValueError(f"Attribution SQL blocked by firewall: {guard_res.error}")

        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            rows = con.execute(guard_res.safe_sql).fetchall()
        finally:
            con.close()

        n_dims = len(dimensions)
        overall_row = None
        single_dim_rows: list[tuple[str, str, int, int, int, int]] = []
        cohort_rows: list[tuple[str, int, int, int, int]] = []

        for r in rows:
            dim_vals = r[:n_dims]
            base_num, base_den, curr_num, curr_den = [int(x or 0) for x in r[n_dims:]]
            non_null = [(dimensions[i], str(dim_vals[i])) for i in range(n_dims) if dim_vals[i] is not None]
            if len(non_null) == 0:
                overall_row = (base_num, base_den, curr_num, curr_den)
            elif len(non_null) == 1:
                single_dim_rows.append((non_null[0][0], non_null[0][1], base_num, base_den, curr_num, curr_den))
            elif len(non_null) == n_dims:
                label = " + ".join(v for _, v in non_null)
                cohort_rows.append((label, base_num, base_den, curr_num, curr_den))

        if not overall_row or overall_row[1] == 0 or overall_row[3] == 0:
            return {"error": "Insufficient data for attribution."}

        b_num, b_den, c_num, c_den = overall_row
        overall_base_rate = b_num / b_den
        overall_curr_rate = c_num / c_den
        total_rate_delta = overall_curr_rate - overall_base_rate

        cohorts: list[SegmentAttribution] = []
        raw_p_vals: list[float] = []

        for label, bn, bd, cn, cd in cohort_rows:
            if cd == 0:
                continue
            r1 = cn / cd
            w1 = cd / c_den
            if bd == 0:
                r0 = overall_base_rate
                w0 = 0.0
                impact = w1 * (r1 - overall_base_rate)
                z_val, p_val, ci = _two_proportion_z_test(b_num, b_den, cn, cd)
            else:
                r0 = bn / bd
                w0 = bd / b_den
                impact = ((w0 + w1) / 2.0) * (r1 - r0) + ((r0 + r1) / 2.0) * (w1 - w0)
                z_val, p_val, ci = _two_proportion_z_test(bn, bd, cn, cd)

            contrib = (impact / total_rate_delta * 100.0) if abs(total_rate_delta) > 1e-9 else 0.0
            raw_p_vals.append(p_val)
            cohorts.append(
                SegmentAttribution(
                    dimension=" × ".join(dimensions),
                    segment=label,
                    baseline_value=r0,
                    current_value=r1,
                    baseline_volume=bd,
                    current_volume=cd,
                    delta_pp_or_abs=r1 - r0,
                    impact_score=impact,
                    contribution_pct=contrib,
                    z_score=z_val,
                    p_value=p_val,
                    ci_95=ci,
                )
            )

        # Apply Benjamini-Hochberg False Discovery Rate adjustment
        q_vals = _benjamini_hochberg(raw_p_vals)
        sig_count = 0
        suppressed_count = 0
        for c, q in zip(cohorts, q_vals):
            c.q_value = q
            c.is_significant = (q <= 0.05) and (c.current_volume >= 15)
            c.significance_label = "SIGNIFICANT (BH-FDR q≤0.05)" if c.is_significant else "NOISE_SUPPRESSED"
            if c.is_significant:
                sig_count += 1
            else:
                suppressed_count += 1

        # Sort significant cohorts first, then by highest contribution to observed movement
        cohorts.sort(key=lambda x: (1 if x.is_significant else 0, x.contribution_pct), reverse=True)

        # Single-dimension breakdown
        single_slices: list[SegmentAttribution] = []
        s_pvals: list[float] = []
        for dim_name, seg_val, bn, bd, cn, cd in single_dim_rows:
            if cd == 0:
                continue
            r1 = cn / cd
            w1 = cd / c_den
            if bd == 0:
                r0 = overall_base_rate
                w0 = 0.0
                impact = w1 * (r1 - overall_base_rate)
                z_val, p_val, ci = _two_proportion_z_test(b_num, b_den, cn, cd)
            else:
                r0 = bn / bd
                w0 = bd / b_den
                impact = ((w0 + w1) / 2.0) * (r1 - r0) + ((r0 + r1) / 2.0) * (w1 - w0)
                z_val, p_val, ci = _two_proportion_z_test(bn, bd, cn, cd)
            contrib = (impact / total_rate_delta * 100.0) if abs(total_rate_delta) > 1e-9 else 0.0
            s_pvals.append(p_val)
            single_slices.append(
                SegmentAttribution(
                    dimension=dim_name,
                    segment=f"{dim_name}={seg_val}",
                    baseline_value=r0,
                    current_value=r1,
                    baseline_volume=bd,
                    current_volume=cd,
                    delta_pp_or_abs=r1 - r0,
                    impact_score=impact,
                    contribution_pct=contrib,
                    z_score=z_val,
                    p_value=p_val,
                    ci_95=ci,
                )
            )
        for s, q in zip(single_slices, _benjamini_hochberg(s_pvals)):
            s.q_value = q
            s.is_significant = q <= 0.05
            s.significance_label = "SIGNIFICANT" if s.is_significant else "NOISE_SUPPRESSED"
        single_slices.sort(key=lambda x: abs(x.contribution_pct), reverse=True)

        check_dim = simpson_dim or dimensions[0]
        kitagawa = self._kitagawa_oaxaca(
            [r for r in single_dim_rows if r[0] == check_dim],
            b_den,
            c_den,
            overall_base_rate,
            overall_curr_rate,
            check_dim,
        )

        rel_change_pct = ((overall_curr_rate - overall_base_rate) / overall_base_rate * 100.0) if overall_base_rate else 0.0

        return {
            "overall": {
                "baseline_rate": round(overall_base_rate, 4),
                "current_rate": round(overall_curr_rate, 4),
                "delta_pp": round(total_rate_delta, 4),
                "relative_change_pct": round(rel_change_pct, 1),
                "baseline_volume": b_den,
                "current_volume": c_den,
                "tested_cohorts": len(cohorts),
                "significant_cohorts": sig_count,
                "noise_suppressed_cohorts": suppressed_count,
            },
            "top_cohorts": [c.to_dict() for c in cohorts[:6]],
            "single_dimensions": [s.to_dict() for s in single_slices[:8]],
            "kitagawa": kitagawa.to_dict(),
            "guard_result": guard_res.to_dict(),
        }

    def _kitagawa_oaxaca(
        self,
        dim_rows: list[tuple[str, str, int, int, int, int]],
        b_den: int,
        c_den: int,
        overall_base_rate: float,
        overall_curr_rate: float,
        dim_name: str,
    ) -> KitagawaDecomposition:
        within_effect = 0.0
        mix_effect = 0.0
        details = []

        for _, seg_val, bn, bd, cn, cd in dim_rows:
            if bd == 0 or cd == 0:
                continue
            r0 = bn / bd
            r1 = cn / cd
            w0 = bd / b_den
            w1 = cd / c_den
            within_i = ((w0 + w1) / 2.0) * (r1 - r0)
            mix_i = ((r0 + r1) / 2.0) * (w1 - w0)
            within_effect += within_i
            mix_effect += mix_i
            details.append({
                "segment": seg_val,
                "baseline_rate": round(r0, 4),
                "current_rate": round(r1, 4),
                "rate_delta_pp": round(r1 - r0, 4),
                "baseline_share": round(w0, 4),
                "current_share": round(w1, 4),
                "within_effect": round(within_i, 4),
                "mix_effect": round(mix_i, 4),
            })

        total_change = overall_curr_rate - overall_base_rate
        paradox = (
            abs(total_change) > 1e-6
            and abs(within_effect) > 1e-6
            and ((total_change < 0 < within_effect) or (total_change > 0 > within_effect))
        )

        explanation = ""
        if paradox:
            explanation = (
                f"Simpson's Paradox detected across `{dim_name}`: overall rate moved {total_change*100:+.2f}pp, "
                f"yet within-segment rates moved {within_effect*100:+.2f}pp. "
                f"A {mix_effect*100:+.2f}pp traffic mix-shift caused the aggregate reversal."
            )

        return KitagawaDecomposition(
            overall_baseline_rate=overall_base_rate,
            overall_current_rate=overall_curr_rate,
            total_change=total_change,
            within_segment_effect=within_effect,
            mix_shift_effect=mix_effect,
            simpsons_paradox=paradox,
            segment_details=details,
            explanation=explanation,
        )
