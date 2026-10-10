"""Mia — локальный AI-ассистент (модульный монолит).

Точка входа нового ядра: ``python -m mia`` запускает текстовый REPL,
подключённый к настоящему Orchestrator (mia.core.orchestrator).

Слои:
    mia.core      — Router → CostEstimator → Policy → TaskContext → Planner
                    → ToolRegistry → AgentLoop → Observation → Verification
    mia.tools     — контракты инструментов и реестр
    mia.ai        — ModelRouter / OllamaProvider (роль chat/coder)
    mia.memory    — profile / episodic / working память
    mia.character — стилевой слой ответов
    mia.config    — централизованная конфигурация ( MiaSettings.from_env )
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
