"""State for the orchestrator graph.

Each branch owns everything it touches. Nothing a branch does can reach
another branch, which is what makes running them on threads safe: the
alternative, one shared evidence list written by every branch, would
have them overwriting each other mid-run.

The step budget is the deliberate exception. One tracker is shared by
every branch so the cap is on total work rather than per branch, and
because several threads increment the same counter it carries a lock.
`self.used += 1` is not atomic, and without the lock parallel branches
quietly lose steps and overrun the cap.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from agentic_rag.core.types import AgentStep, Evidence


@dataclass
class BranchState:
    index: int
    question: str
    evidence: list[Evidence] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    error: str = ""

    def summary(self) -> dict:
        return {
            "index": self.index,
            "question": self.question,
            "evidence_count": len(self.evidence),
            "step_count": len(self.steps),
            "error": self.error,
        }


class BudgetTracker:
    """Total tool calls allowed across every branch of one question."""

    def __init__(self, max_steps: int):
        self.max_steps = max(1, max_steps)
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        """Claim one step. False means the budget is gone and the caller should finish."""
        with self._lock:
            if self.used >= self.max_steps:
                return False
            self.used += 1
            return True

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_steps - self.used)

    def snapshot(self) -> dict:
        with self._lock:
            return {"used": self.used, "max_steps": self.max_steps}
