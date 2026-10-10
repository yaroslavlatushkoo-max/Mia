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
from .session import Session, PendingTask, PendingState

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
        session: Optional[Session] = None,
    ):
        self.router = router or Router()
        self.cost_estimator = cost_estimator or CostEstimator()
        self.policy = policy or PolicyEngine()
        self.tool_registry = tool_registry or register_builtin_tools(ToolRegistry())
        self.stylist = stylist or ResponseStylist()
        self.model_router = model_router or ModelRouter()
        # Память явно привязана к конфигурации: Orchestrator(memory=...) —
        # приоритет вызывающего кода; иначе безопасный default из mia.config
        # (НЕ зависит от CWD запуска, не пишет молча в пользовательское
        # хранилище из тестов/временных экземпляров).
        self.memory = memory or MemoryRetriever()
        self.responder = responder or Responder(stylist=self.stylist)
        # Session + HITL (To-do #1): working state and at most one pending
        # task per session. handle() accepts an explicit session argument;
        # this default keeps backward compatibility for existing callers.
        self.session = session or Session()

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

    def handle(self, user_input: str, source: str = "text",
               session: Optional[Session] = None) -> dict:
        sess = session or self.session

        # ---- HITL resume (To-do #1): a pending task takes precedence ----
        resume = sess.try_resume(user_input)
        if resume is not None:
            kind = resume["kind"]

            if kind == "confirm":
                return self._resume_confirmed(resume["pending"], sess, user_input)

            if kind == "cancel":
                p = resume["pending"]
                sess.clear_pending()
                answer = self.responder.direct_response(
                    TaskContext(raw_input=user_input),
                    f"Хорошо, отменила задачу «{p.raw_input}». Ничего не выполняла.",
                )
                sess.add_message("user", user_input)
                sess.add_message("assistant", answer)
                return {
                    "type": "cancelled",
                    "answer": answer,
                    "pending": None,
                    "resumed_task_id": p.task_id,
                }

            if kind == "clarify":
                return self._resume_clarified(resume["pending"], sess, user_input)

            # kind == "waiting": still no confirmation/clarification.
            p = resume["pending"]
            answer = self.responder.direct_response(
                TaskContext(raw_input=user_input),
                f"Задача «{p.raw_input}» всё ещё ожидает подтверждения. "
                f"Скажите «да», чтобы продолжить, или «нет», чтобы отменить.",
            )
            return {
                "type": "waiting",
                "answer": answer,
                "pending": p.to_dict(),
                "resumed_task_id": p.task_id,
            }

        ctx = self.router.route(user_input, source=source)
        ctx.session_id = sess.session_id
        budget = self.cost_estimator.estimate(ctx)
        ctx = self.policy.evaluate(ctx)

        trace = ExecutionTrace(task_id=ctx.task_id)
        trace.status = ExecutionStatus.ROUTED
        trace.max_steps = budget.max_steps

        # ---- CLARIFY intent: ask instead of guessing (To-do #3) ----
        if ctx.intent == "CLARIFY":
            question = ctx.entities.get("question") or (
                f"Уточни, пожалуйста, что именно сделать: «{ctx.raw_input}»."
            )
            sess.pending_task = PendingTask(
                task_id=ctx.task_id,
                raw_input=ctx.raw_input,
                intent=ctx.intent,
                state=PendingState.WAITING_CLARIFICATION,
                reason=ctx.entities.get("clarify_reason", "low confidence"),
                entities=dict(ctx.entities),
            )
            answer = self.responder.direct_response(ctx, question)
            trace.status = ExecutionStatus.WAITING_TOOL
            trace.final_answer = answer
            sess.add_message("user", user_input)
            sess.add_message("assistant", answer)
            return {
                "type": "clarify",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
                "pending": sess.pending_task.to_dict(),
            }

        # ---- CANCEL: drop any pending task honestly (To-do #3) ----
        if ctx.intent == "CANCEL":
            had_pending = sess.pending_task is not None
            sess.clear_pending()
            answer = self.responder.direct_response(
                ctx,
                "Отменила текущую задачу." if had_pending
                else "Сейчас нет активной задачи, которую можно отменить.",
            )
            trace.status = ExecutionStatus.CANCELLED
            trace.final_answer = answer
            sess.add_message("user", user_input)
            sess.add_message("assistant", answer)
            return {
                "type": "cancelled",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
                "pending": None,
            }

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

        # ---- HITL: Policy blocked a risky action -> WAITING_CONFIRMATION --
        verification = agent_result.get("verification") or {}
        if (
            verification.get("policy_blocked")
            and not verification.get("success")
            and ctx.requires_confirmation
        ):
            sess.pending_task = PendingTask(
                task_id=ctx.task_id,
                raw_input=ctx.raw_input,
                intent=ctx.intent,
                state=PendingState.WAITING_CONFIRMATION,
                reason="; ".join(verification.get("reasons", []))[:200],
                entities=dict(ctx.entities),
            )
            trace.status = ExecutionStatus.WAITING_TOOL
            answer = self.responder.direct_response(
                ctx,
                f"Это рискованное действие ({ctx.intent.lower()}) требует твоего "
                f"подтверждения. Выполнить «{ctx.raw_input}»? Ответь «да» или «нет».",
            )
            trace.final_answer = answer
            sess.add_message("user", user_input)
            sess.add_message("assistant", answer)
            return {
                "type": "confirmation_required",
                "context": ctx.to_dict(),
                "budget": budget.__dict__,
                "trace": trace.to_dict(),
                "answer": answer,
                "plan": agent_result.get("plan"),
                "verification": verification,
                "pending": sess.pending_task.to_dict(),
            }

        self.memory.episodic.add_episode(
            event_type="task",
            content=f"Task: {user_input[:100]}",
            importance=3
        )
        sess.add_message("user", user_input)
        sess.add_message("assistant", agent_result["answer"])

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

    # ------------------------------------------------------------------
    # HITL resume paths (To-do #1)
    # ------------------------------------------------------------------
    def _resume_confirmed(self, p: PendingTask, sess: Session, user_text: str) -> dict:
        """Resume the SAME pending task after explicit confirmation.

        The original TaskContext is rebuilt with its ORIGINAL task_id and
        entities (continuation, not a new task from scratch). Confirmation
        only sets ctx.confirmed=True, which Policy re-evaluates at the
        normal enforcement point — nothing bypasses Policy here.
        """
        ctx = self.router.route(p.raw_input)
        ctx.task_id = p.task_id              # same task identity
        ctx.session_id = sess.session_id
        ctx.entities = dict(p.entities)      # original deterministic entities
        ctx.confirmed = True                 # consumed by Policy.check_tool

        budget = self.cost_estimator.estimate(ctx)
        ctx = self.policy.evaluate(ctx)

        trace = ExecutionTrace(task_id=ctx.task_id)
        trace.status = ExecutionStatus.ROUTED
        trace.max_steps = budget.max_steps

        agent_result = self.agent_loop.run(ctx, trace)
        sess.clear_pending()

        verification = agent_result.get("verification") or {}
        self.memory.episodic.add_episode(
            event_type="task",
            content=f"Confirmed task: {p.raw_input[:100]}",
            importance=4,
        )
        sess.add_message("user", user_text)
        sess.add_message("assistant", agent_result["answer"])

        return {
            "type": "resumed",
            "resumed_task_id": p.task_id,
            "context": ctx.to_dict(),
            "budget": budget.__dict__,
            "trace": trace.to_dict(),
            "answer": agent_result["answer"],
            "plan": agent_result.get("plan"),
            "verification": verification,
            "replans": agent_result.get("replans", 0),
            "pending": None,
        }

    def _resume_clarified(self, p: PendingTask, sess: Session, user_text: str) -> dict:
        """Resume after CLARIFY: refine the ORIGINAL request with the
        user's answer and reroute it deterministically (no guessing)."""
        merged_raw = f"{p.raw_input} {user_text}".strip()
        # Clear the pending clarification BEFORE rerouting. Otherwise the
        # recursive handle() would see the stale WAITING_CLARIFICATION task
        # via try_resume() and re-enter this method indefinitely
        # (RecursionError). If the merged request is still ambiguous, the
        # reroute will honestly set a fresh pending clarification.
        sess.clear_pending()
        result = self.handle(merged_raw, session=sess)
        result["resumed_task_id"] = p.task_id
        result["clarified_from"] = p.raw_input
        return result

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