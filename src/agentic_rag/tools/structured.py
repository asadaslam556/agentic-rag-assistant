"""Structured-data tools: a safe calculator and a product/metric API.

These stand in for the "APIs and functions" branch of the architecture:
deterministic tools that return exact structured facts rather than
retrieved prose. ``KnowledgeBaseTool`` reads a JSON catalog; in a real
deployment the same interface would wrap a SQL database or a REST API.
"""

from __future__ import annotations

import ast
import json
import operator
from pathlib import Path

from agentic_rag.core.textutils import content_tokens
from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.tools.base import Tool, ToolSpec

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def safe_eval(expression: str) -> float:
    """Evaluate a pure arithmetic expression via the AST; nothing else runs."""
    expression = expression.strip()
    if not expression or len(expression) > 200:
        raise ValueError("Expression must be 1-200 characters of arithmetic.")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow):
                left, right = _eval(node.left), _eval(node.right)
                if abs(right) > 12 or abs(left) > 10**6:
                    raise ValueError("Exponent out of allowed range.")
                return _OPS[ast.Pow](left, right)
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = _eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        raise ValueError(f"Unsupported syntax: {ast.dump(node)[:60]}")

    tree = ast.parse(expression, mode="eval")
    return _eval(tree)


def format_number(value: float) -> str:
    if value == int(value) and abs(value) < 10**15:
        return f"{int(value):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


class CalculatorTool(Tool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="calculator",
            description="Evaluate an arithmetic expression exactly (e.g. totals, percentages).",
            parameters={"expression": "Arithmetic only, e.g. '23 * 649' or '(449 + 649) / 2'."},
            required=["expression"],
        )

    def run(self, expression: str) -> ToolResult:
        result = safe_eval(str(expression))
        rendered = format_number(result)
        text = f"Calculation: {expression} = {rendered}"
        evidence = Evidence(
            id="",
            text=text,
            source_type="calculation",
            source_ref="calculator",
            title="Calculator",
            tool_name="calculator",
            rank=0,
            score=1.0,
        )
        return ToolResult(evidence=[evidence], observation=text)


class KnowledgeBaseTool(Tool):
    """Lookup against a structured product catalog and company metrics."""

    def __init__(self, catalog_path: str | Path):
        self.catalog_path = Path(catalog_path)
        self.spec = ToolSpec(
            name="knowledge_base",
            description=(
                "Query structured records: product catalog entries (SKU, price, specs) "
                "and company metrics. Returns exact values."
            ),
            parameters={"query": "Product name, SKU, or metric keywords, e.g. 'Atlas P2 price'."},
            required=["query"],
        )

    def _load(self) -> dict:
        if not self.catalog_path.exists():
            return {"products": [], "company_metrics": {}}
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    @staticmethod
    def _format_product(product: dict) -> str:
        parts = [f"{product.get('name', '?')} (SKU {product.get('sku', '?')})"]
        for key, label in [
            ("category", "category"),
            ("list_price_eur", "list price EUR"),
            ("lease_eur_month", "lease EUR/month"),
            ("payload_kg", "payload kg"),
            ("runtime_hours", "runtime hours"),
            ("status", "status"),
        ]:
            if key in product:
                parts.append(f"{label}: {product[key]}")
        if product.get("notes"):
            parts.append(f"notes: {product['notes']}")
        return "; ".join(str(p) for p in parts)

    def run(self, query: str) -> ToolResult:
        catalog = self._load()
        query_tokens = content_tokens(str(query))
        evidence: list[Evidence] = []
        lines: list[str] = []
        rank = 0

        scored: list[tuple[int, dict]] = []
        for product in catalog.get("products", []):
            haystack = content_tokens(
                " ".join(str(product.get(k, "")) for k in ("sku", "name", "category", "notes"))
            )
            overlap = len(query_tokens & haystack)
            if overlap:
                scored.append((overlap, product))
        for overlap, product in sorted(scored, key=lambda item: -item[0])[:3]:
            text = self._format_product(product)
            evidence.append(
                Evidence(
                    id="",
                    text=text,
                    source_type="structured",
                    source_ref=f"{self.catalog_path.name}#sku={product.get('sku', '?')}",
                    title=f"Catalog: {product.get('name', product.get('sku', '?'))}",
                    tool_name="knowledge_base",
                    rank=rank,
                    score=float(overlap),
                )
            )
            lines.append(f"  - {text}")
            rank += 1

        for key, value in catalog.get("company_metrics", {}).items():
            key_tokens = content_tokens(key.replace("_", " "))
            if query_tokens & key_tokens:
                text = f"Company metric {key.replace('_', ' ')}: {value}"
                evidence.append(
                    Evidence(
                        id="",
                        text=text,
                        source_type="structured",
                        source_ref=f"{self.catalog_path.name}#metric={key}",
                        title=f"Metric: {key.replace('_', ' ')}",
                        tool_name="knowledge_base",
                        rank=rank,
                        score=1.0,
                    )
                )
                lines.append(f"  - {text}")
                rank += 1

        if not evidence:
            return ToolResult(evidence=[], observation=f"No structured records matched {query!r}.")
        return ToolResult(
            evidence=evidence,
            observation=f"Structured lookup for {query!r} returned {len(evidence)} record(s):\n"
            + "\n".join(lines),
        )
