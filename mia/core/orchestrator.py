from __future__ import annotations

from typing import Optional

from .router import Router
from .cost_estimator import CostEstimator
from .policy import PolicyEngine
from .task_context import TaskContext, TaskMode
from .execution_trace import ExecutionTrace, ExecutionStatus
from .agent_loop import AgentLoop
from .planner import Planner
from .verifier import Verifier
from .responder import Responder

from ..tools.registry import ToolRegistry
from ..tools.builtin_tools import register_builtin_tools
from ..character.response_stylist import ResponseStylist
from ..ai.model_router import ModelRouter
from ..memory.memory_retriever import MemoryRetriever


class Orchestrator:
    def __init__(
        self,
        router: Optional[Router] = None,
        cost_estimator: Optional[CostEstimator] = None,
        policy: Optional[PolicyEngine] = None,
        tool_registry: Optional[ToolRegistry] = None,
        stylist: Optional[ResponseStylist] = None,
        agent_loop: Optional[AgentLoop] = None,
        model_router: Optional[ModelRouter] = None,
        memory: Optional[MemoryRetriever] = None,
        responder: Optional[Responder] = None,
    ):
        self.router = router or Router()
        self.cost_estimator = cost_estimator or CostEstimator()
        self.policy = policy or PolicyEngine()
        self.tool_registry = tool_registry or register_builtin_tools(ToolRegistry())
        self.stylist = stylist or ResponseStylist()
        self.model_router = model_router or ModelRouter()
        self.memory = memory or MemoryRetriever()
        self.responder = responder or Responder(stylist=self.stylist)

        # Planner receives capabilities from the ToolRegistry — the single
        # source of truth (CORE_MIGRATION.md §5). LLM is an enhancement;
        # rule-based fallback stays working.
        planner = Planner(model_router=self.model_router, tool_registry=self.tool_registry)
        verifier = Verifier(model_router=self.model_router)
        self.agent_loop = agent_loop or AgentLoop(
            self.tool_registry,
            planner,
            verifier,
            policy=self.policy,
            responder=self.responder,
        )

    def handle(self, user_input: str, source: str = "text") -> dict:
        ctx = self.router.route(user_input, source=source)
        budget = self.cost_estimator.estimate(ctx)
        ctx = self.policy.evaluate(ctx)

        trace = ExecutionTrace(task_id=ctx.task_id)
        trace.status = ExecutionStatus.ROUTED
        trace.max_steps = budget.max_steps

        if ctx.intent == "USER_FACT":
            answer = self._direct_response(ctx)
            self.memory.extract_and_remember(user_input, answer)
            trace.status = ExecutionStatus.COMPLETED
            trace.final_answer = answer
            return {
                "type": "direct",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
            }

        if ctx.intent == "MEMORY_QUERY":
            answer = self.memory.answer_memory_query(user_input)
            trace.status = ExecutionStatus.COMPLETED
            trace.final_answer = answer
            return {
                "type": "direct",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
            }

        if ctx.mode in {TaskMode.COMPANION, TaskMode.ASSISTANT} and ctx.complexity in {"C0", "C1"}:
            answer = self._direct_response(ctx)
            self.memory.extract_and_remember(user_input, answer)
            self.memory.working.add_message("user", user_input)
            self.memory.working.add_message("assistant", answer)
            trace.status = ExecutionStatus.COMPLETED
            trace.final_answer = answer
            return {
                "type": "direct",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
            }

        agent_result = self.agent_loop.run(ctx, trace)
        self.memory.episodic.add_episode(
            event_type="task",
            content=f"Task: {user_input[:100]}",
            importance=3
        )

        return {
            "type": "agent",
            "context": ctx.to_dict(),
            "budget": budget.__dict__,
            "trace": trace.to_dict(),
            "answer": agent_result["answer"],
            "plan": agent_result.get("plan"),
            "verification": agent_result.get("verification"),
            "replans": agent_result.get("replans", 0),
        }

    def _direct_response(self, ctx: TaskContext) -> str:
        # Direct path builds a factual answer first, then the Responder
        # applies the character layer (reasoning and styling stay separate).
        if ctx.intent == "GREETING":
            local = self._try_local_answer(ctx, "Привет! Ответь коротко и тепло как Мия.")
            return self.responder.direct_response(
                ctx, local or "Привет~ Мия на связи. Что будем делать сегодня?"
            )

        if ctx.intent == "FAREWELL":
            local = self._try_local_answer(ctx, "Пользователь прощается. Ответь коротко и тепло.")
            return self.responder.direct_response(
                ctx, local or "Пока~ Возвращайся, когда понадобится помощь. Мия будет на связи."
            )

        local = self._try_local_answer(ctx, ctx.raw_input)
        if local:
            return self.responder.direct_response(ctx, local)

        return self.responder.direct_response(
            ctx, "Я поняла запрос. Скоро здесь будет полноценный ответ через локальную модель."
        )

    def _try_local_answer(self, ctx: TaskContext, prompt: str) -> Optional[str]:
        try:
            memory_context = self.memory.get_context_for_query(prompt)
            enriched_prompt = f"""Контекст о пользователе: {memory_context['profile_summary']}

Запрос пользователя: {prompt}

Ответ:"""
            response = self.model_router.generate(
                prompt=enriched_prompt,
                system_prompt=self.stylist.system_prompt(ctx.mode.value),
                max_tokens=220 if ctx.complexity == "C0" else 512,
                preferred="chat",
            )
            if response.error:
                return None
            return response.text
        except Exception:
            return None