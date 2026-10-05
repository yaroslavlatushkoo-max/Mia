from __future__ import annotations

from typing import Any, Dict, List, Optional


class Verifier:
    def __init__(self, model_router=None):
        self.model_router = model_router

    def verify_plan_execution(self, plan, trace) -> Dict[str, Any]:
        # Базовая проверка
        checks = []
        successful_steps = 0

        for step in trace.steps:
            check = {
                "step_index": step.step_index,
                "action": step.action,
                "tool": step.tool,
                "success": step.status == "success" and step.error is None,
                "error": step.error,
            }
            checks.append(check)
            if check["success"]:
                successful_steps += 1

        basic_success = successful_steps > 0 and successful_steps >= len(plan.steps) * 0.5

        # Semantic verification через LLM
        semantic_check = None
        if self.model_router and trace.steps:
            semantic_check = self._semantic_verify(plan, trace)

        final_success = basic_success
        if semantic_check is not None:
            final_success = final_success and semantic_check.get("success", True)

        return {
            "success": final_success,
            "basic_success": basic_success,
            "semantic_check": semantic_check,
            "checks": checks,
            "summary": f"{successful_steps}/{len(trace.steps)} steps succeeded"
        }

    def _semantic_verify(self, plan, trace) -> Optional[Dict[str, Any]]:
        try:
            steps_summary = "\n".join([
                f"- {s.action}: {'OK' if s.status == 'success' else 'FAIL: ' + str(s.error)}"
                for s in trace.steps
            ])

            prompt = f"""Проверь, достигнута ли цель задачи.

Цель: {plan.goal}

Выполненные шаги:
{steps_summary}

Ответь строго:
SUCCESS: yes/no
REASON: <краткое объяснение>"""

            response = self.model_router.generate(
                prompt=prompt,
                system_prompt="Ты проверяющий качества. Отвечай только yes/no и причину.",
                max_tokens=128,
                preferred="chat"
            )

            if response.error or not response.text:
                return None

            text = response.text.lower()
            success = "success: yes" in text or "успех: да" in text

            return {
                "success": success,
                "reason": response.text
            }

        except Exception as e:
            print(f"[Verifier] Semantic check error: {e}")
            return None