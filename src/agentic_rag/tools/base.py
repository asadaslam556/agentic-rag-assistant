"""Tool interface for the agent orchestrator.

Every tool returns a ``ToolResult``: structured ``Evidence`` objects for
downstream context assembly plus a compact human-readable observation
string that goes back into the agent's transcript.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentic_rag.core.types import ToolResult


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str] = field(default_factory=dict)  # param -> description
    required: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"- {self.name}: {self.description}"]
        for param, doc in self.parameters.items():
            marker = " (required)" if param in self.required else ""
            lines.append(f"    - {param}{marker}: {doc}")
        return "\n".join(lines)


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        ...

    def safe_run(self, **kwargs: Any) -> ToolResult:
        """Run with arguments filtered to the spec; never raise into the agent loop."""
        allowed = {k: v for k, v in kwargs.items() if k in self.spec.parameters}
        missing = [p for p in self.spec.required if p not in allowed]
        if missing:
            return ToolResult(evidence=[], observation=f"Error: missing required parameter(s): {', '.join(missing)}.")
        try:
            return self.run(**allowed)
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent as an observation
            return ToolResult(evidence=[], observation=f"Error while running {self.spec.name}: {exc}")


def preview(text: str, limit: int = 240) -> str:
    """Shorten a passage for a trace line without cutting a word in half.

    A hard slice landed mid-number and produced things like "EUR 64...",
    which a model reads as missing data: it then searches again for a figure
    it already has. Backing up to the last space keeps tokens whole, and the
    observation says outright that the full text is coming.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(",.;:") + " [...]"
