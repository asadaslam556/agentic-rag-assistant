"""Which model handles which job.

A run touches the model in several distinct roles, and they do not all
need the same one. Planning tool calls, splitting a question, rewriting
a follow-up, and scoring an eval are mechanical and cheap. Writing the
answer and checking its claims are where quality shows. Splitting those
across a fast model and a strong one costs less and is usually better
than sending everything to one model.

Nothing here is hardcoded. With only LLM_MODEL set, every role uses it
and behaviour is exactly as before. Setting LLM_MODEL_FAST and
LLM_MODEL_DEEP turns on the two tiers, and LLM_MODEL_<ROLE> pins a
single role. Clients are cached per model name, so roles that resolve
to the same model share one client.
"""

from __future__ import annotations

import dataclasses

from agentic_rag.config import ROLES, Settings
from agentic_rag.llm.base import LLMClient
from agentic_rag.llm.providers import build_client

# Roles that are mechanical enough for the cheaper model. The split is a
# default, not a rule: any role can be pinned with LLM_MODEL_<ROLE>.
FAST_ROLES = frozenset({"plan", "decompose", "rewrite", "judge"})


class ModelRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._clients: dict[str, LLMClient] = {}

    def model_for(self, role: str) -> str:
        """Resolve a role to a model name, most specific setting wins."""
        pinned = self.settings.llm_role_models.get(role)
        if pinned:
            return pinned
        if role in FAST_ROLES and self.settings.llm_model_fast:
            return self.settings.llm_model_fast
        if role not in FAST_ROLES and self.settings.llm_model_deep:
            return self.settings.llm_model_deep
        return self.settings.llm_model

    def client_for(self, role: str) -> LLMClient:
        model = self.model_for(role)
        if model not in self._clients:
            settings = (
                self.settings
                if model == self.settings.llm_model
                else dataclasses.replace(self.settings, llm_model=model)
            )
            self._clients[model] = build_client(settings)
        return self._clients[model]

    def default_client(self) -> LLMClient:
        """The client for synthesis, which is what the pipeline treats as primary."""
        return self.client_for("synthesize")

    def describe(self) -> dict:
        """Role to model map, for rag stats and the health endpoint."""
        return {role: self.model_for(role) or "provider default" for role in ROLES}

    def is_split(self) -> bool:
        return len({self.model_for(role) for role in ROLES}) > 1
