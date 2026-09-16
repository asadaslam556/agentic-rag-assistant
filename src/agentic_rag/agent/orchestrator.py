"""The agent orchestrator: a provider-agnostic plan-and-act loop.

The LLM receives the tool catalog and replies with one JSON decision
per step: call a tool or finish. Tool observations are fed back into
the transcript, evidence is accumulated for context assembly, and the
loop guards against invalid JSON, unknown tools, and repeated calls.
Using a plain JSON protocol instead of provider-specific tool-calling
APIs keeps the loop identical across OpenAI, Azure, Anthropic, local
models, and the offline mock.
"""

from __future__ import annotations

import json

from agentic_rag.agent.parser import ParserError, extract_first_json
from agentic_rag.agent.prompts import build_plan_system
from agentic_rag.config import Settings
from agentic_rag.core.types import AgentStep, Evidence
from agentic_rag.llm.base import LLMClient
from agentic_rag.tools import render_tool_catalog
from agentic_rag.tools.base import Tool

_RETRY_NOTE = (
    "Your last reply was not a single valid JSON object. Respond with exactly one "
    'JSON object: {"thought": "...", "action": "<tool name or finish>", "action_input": {...}}'
)


class Orchestrator:
    def __init__(self, llm: LLMClient, tools: dict[str, Tool], settings: Settings):
        self.llm = llm
        self.tools = tools
        self.settings = settings
        self._system = build_plan_system(render_tool_catalog(tools), settings.max_agent_steps)

    def collect(
        self, question: str, on_step=None, budget=None
    ) -> tuple[list[Evidence], list[AgentStep]]:
        """Run the plan-and-act loop; return all evidence plus the step trace.

        on_step, when given, is called with each AgentStep as it happens,
        which is what powers the live trace in the streaming API.

        budget, when given, is a BudgetTracker shared with any sibling
        branches. Once it runs out the loop stops planning and finishes
        with what it has, so several branches together cannot run past
        the cap the way they would with only a per-loop limit."""
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": f"QUESTION: {question}\nBegin. Respond with exactly one JSON object.",
            }
        ]
        evidence: list[Evidence] = []
        steps: list[AgentStep] = []
        seen_calls: set[str] = set()
        call_id = 0
        observation_index = 0
        parse_failures = 0

        for step_number in range(1, self.settings.max_agent_steps + 1):
            if budget is not None and not budget.take():
                steps.append(
                    AgentStep(
                        step=step_number,
                        thought="Shared step budget is used up, finishing with what we have.",
                        action="finish",
                        action_input={},
                        observation="Budget exhausted.",
                    )
                )
                if on_step is not None:
                    on_step(steps[-1])
                break
            response = self.llm.complete(
                self._system, messages, temperature=self.settings.llm_temperature, max_tokens=500
            )
            try:
                decision = extract_first_json(response.text)
            except ParserError:
                parse_failures += 1
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": _RETRY_NOTE})
                if parse_failures >= 3:
                    break
                continue

            thought = str(decision.get("thought", "")).strip()
            action = str(decision.get("action", "")).strip()
            action_input = decision.get("action_input")
            if not isinstance(action_input, dict):
                action_input = {}

            messages.append({"role": "assistant", "content": response.text})

            if action in {"finish", "final", "done", ""}:
                steps.append(
                    AgentStep(
                        step=step_number,
                        thought=thought,
                        action="finish",
                        action_input={},
                        observation="Evidence collection finished.",
                    )
                )
                if on_step is not None:
                    on_step(steps[-1])
                break

            tool = self.tools.get(action)
            if tool is None:
                observation = (
                    f"Unknown tool {action!r}. Available tools: {', '.join(self.tools)}. "
                    "Choose one of these or finish."
                )
            else:
                call_key = f"{action}:{json.dumps(action_input, sort_keys=True, default=str)}"
                if call_key in seen_calls:
                    observation = (
                        "You already ran this exact call. Choose a different action, "
                        "refine the input, or finish."
                    )
                else:
                    seen_calls.add(call_key)
                    call_id += 1
                    result = tool.safe_run(**action_input)
                    for item in result.evidence:
                        item.id = f"e{len(evidence) + 1}"
                        item.call_id = call_id
                        evidence.append(item)
                    observation = result.observation

            observation_index += 1
            steps.append(
                AgentStep(
                    step=step_number,
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation[:400],
                )
            )
            if on_step is not None:
                on_step(steps[-1])
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"OBSERVATION {observation_index} ({action}): {observation}\n"
                        "Continue. Respond with exactly one JSON object."
                    ),
                }
            )
        return evidence, steps
