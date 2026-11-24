"""Parses dbt target/manifest.json and extracts model/column lineage via sqlglot."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from backend.config import MANIFEST_PATH


@dataclass
class ModelNode:
    unique_id: str
    name: str
    resource_type: str
    schema: str
    alias: str
    relation_name: str
    description: str
    meta: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    compiled_code: str = ""
    raw_code: str = ""


class ManifestGraph:
    """In-memory graph of dbt models, grains, metrics, and lineage."""

    def __init__(self, manifest_path: Path = MANIFEST_PATH) -> None:
        self.manifest_path = manifest_path
        self.nodes: dict[str, ModelNode] = {}
        self.by_name: dict[str, ModelNode] = {}
        self.by_relation: dict[str, ModelNode] = {}
        self.parent_map: dict[str, list[str]] = {}
        self.child_map: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"dbt manifest not found at {self.manifest_path}. Run `dbt build` first.")

        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.parent_map = data.get("parent_map", {})
        self.child_map = data.get("child_map", {})

        for uid, raw in {**data.get("nodes", {}), **data.get("sources", {})}.items():
            rtype = raw.get("resource_type", "")
            if rtype not in {"model", "source"}:
                continue
            schema = raw.get("schema", "main")
            alias = raw.get("alias") or raw.get("name", "")
            relation = raw.get("relation_name") or f"{schema}.{alias}"
            # Normalize DuckDB relation quotes for clean lookup
            clean_rel = relation.replace('"', "")
            meta = raw.get("meta") or raw.get("config", {}).get("meta", {}) or {}
            node = ModelNode(
                unique_id=uid,
                name=raw.get("name", ""),
                resource_type=rtype,
                schema=schema,
                alias=alias,
                relation_name=clean_rel,
                description=raw.get("description", ""),
                meta=meta,
                depends_on=raw.get("depends_on", {}).get("nodes", []),
                compiled_code=raw.get("compiled_code", "") or raw.get("compiled_sql", ""),
                raw_code=raw.get("raw_code", "") or raw.get("raw_sql", ""),
            )
            self.nodes[uid] = node
            self.by_name[node.name] = node
            self.by_relation[clean_rel.lower()] = node
            # Also register without catalog prefix if present (e.g. metricpulse.main_marts.fct_revenue -> main_marts.fct_revenue)
            parts = clean_rel.split(".")
            if len(parts) >= 2:
                self.by_relation[".".join(parts[-2:]).lower()] = node
            self.by_relation[alias.lower()] = node

    def get_node(self, name_or_id: str) -> ModelNode | None:
        if name_or_id in self.nodes:
            return self.nodes[name_or_id]
        if name_or_id in self.by_name:
            return self.by_name[name_or_id]
        return self.by_relation.get(name_or_id.replace('"', "").lower())

    def get_upstream_nodes(self, model_name: str, include_self: bool = False) -> list[ModelNode]:
        """BFS walk upstream along dbt parent_map."""
        root = self.get_node(model_name)
        if not root:
            return []
        visited: set[str] = set()
        queue: deque[str] = deque([root.unique_id])
        result: list[ModelNode] = []

        while queue:
            cur_id = queue.popleft()
            if cur_id in visited:
                continue
            visited.add(cur_id)
            node = self.nodes.get(cur_id)
            if node and (include_self or cur_id != root.unique_id):
                result.append(node)
            for parent_id in self.parent_map.get(cur_id, []):
                if parent_id not in visited and parent_id in self.nodes:
                    queue.append(parent_id)
        return result

    def get_lineage_dag(self, model_name: str, node_health: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """Return nodes and directed edges (upstream -> downstream) for UI rendering."""
        root = self.get_node(model_name)
        if not root:
            return {"nodes": [], "edges": []}

        upstream = self.get_upstream_nodes(model_name, include_self=True)
        uid_set = {n.unique_id for n in upstream}
        health_map = node_health or {}

        # Assign layer depth for clean left-to-right DAG layout
        layer_order = {"source": 0, "staging": 1, "intermediate": 2, "marts": 3}

        dag_nodes = []
        for n in upstream:
            if n.resource_type == "source":
                layer = 0
                tier = "source"
            elif n.name.startswith("stg_"):
                layer = 1
                tier = "staging"
            elif n.name.startswith("int_"):
                layer = 2
                tier = "intermediate"
            else:
                layer = 3
                tier = "mart"

            h = health_map.get(n.name, {})
            dag_nodes.append({
                "id": n.name,
                "unique_id": n.unique_id,
                "label": n.name,
                "tier": tier,
                "layer": layer_order.get(tier, layer),
                "relation_name": n.relation_name,
                "grain": n.meta.get("grain", "unknown"),
                "primary_key": n.meta.get("primary_key"),
                "status": h.get("status", "HEALTHY"),
                "diagnostics": h,
            })

        edges = []
        for n in upstream:
            for p_id in self.parent_map.get(n.unique_id, []):
                if p_id in uid_set and p_id in self.nodes:
                    edges.append({
                        "source": self.nodes[p_id].name,
                        "target": n.name,
                    })

        return {"nodes": dag_nodes, "edges": edges}

    def get_column_lineage(self, model_name: str, column_name: str) -> list[str]:
        """Extract upstream source columns referenced by a model's compiled SQL using sqlglot."""
        node = self.get_node(model_name)
        if not node or not node.compiled_code:
            return []
        try:
            tree = sqlglot.parse_one(node.compiled_code, read="duckdb")
        except Exception:
            return []

        refs: list[str] = []
        for col in tree.find_all(exp.Column):
            if col.name.lower() == column_name.lower() or column_name == "*":
                tbl = col.table or node.name
                refs.append(f"{tbl}.{col.name}")
        return sorted(set(refs))
