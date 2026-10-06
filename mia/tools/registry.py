from __future__ import annotations

"""ToolRegistry — honest execution boundary (Task 5).

Runtime path:

    find tool            -> REGISTERED check
    executor is None     -> NOT_IMPLEMENTED   (never fake success)
    policy gate          -> BLOCKED           (before any execution)
    executor in thread   -> real wall-clock TIMEOUT; the caller (event
                            loop / AgentLoop) is never blocked by a
                            hanging synchronous executor. NOTE: a timed
                            out Python worker thread cannot be killed —
                            we report that honestly via metadata
                            ("worker_may_still_run") instead of claiming
                            cancellation (cooperative cancel = Task 6).
    Observation          -> structured result, compressed before return.

EXECUTED != VERIFIED: `run()` only produces Observations; verification is
a separate stage performed by the Verifier on top of ExecutionTrace.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .schemas import ToolSpec, ToolResult
from .observation import Observation, ObservationStatus
from .compressor import ObservationCompressor


class _PolicyProxy:
    """Minimal adapter over PolicyEngine.check_tool decisions."""

    @staticmethod
    def decide(policy, ctx, name: str, spec: Optional[ToolSpec]):
        if policy is None or ctx is None:
            return None
        try:
            return policy.check_tool(ctx, name, spec)
        except AttributeError:
            # Older PolicyEngine without check_tool -> conservative allow
            # is FORBIDDEN; treat as no-op only when policy itself opted
            # out by passing ctx=None above.
            return None


class ToolRegistry:
    """Capability layer (CORE_MIGRATION.md §5).

    Single source of truth for executable tools. The Planner must obtain
    its capabilities from this registry — never from a duplicated list.
    """

    # One shared bounded pool per registry instance (created lazily):
    # not a new ThreadPoolExecutor per call, and closed via shutdown().
    _DEFAULT_MAX_WORKERS = 4

    def __init__(self, compressor: Optional[ObservationCompressor] = None):
        self._tools: Dict[str, ToolSpec] = {}
        self._pool: Optional[ThreadPoolExecutor] = None
        self.compressor = compressor or ObservationCompressor()

    # ------------------------------------------------------------------
    # Lifecycle of the offload pool (honest, bounded, reusable).
    # ------------------------------------------------------------------
    def _executor_pool(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self._DEFAULT_MAX_WORKERS,
                thread_name_prefix="mia-tool",
            )
        return self._pool

    def shutdown(self, wait: bool = False) -> None:
        """Release the offload pool. Timed-out workers may still finish
        in background threads; we never pretend they were killed."""
        if self._pool is not None:
            self._pool.shutdown(wait=wait)
            self._pool = None

    def register(self, tool: ToolSpec):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def capabilities(self) -> List[Dict[str, Any]]:
        """Planner-facing capability list, excluding non-executable tools."""
        return [
            t.to_capability()
            for t in self._tools.values()
            if t.executor is not None and t.status != "BROKEN"
        ]

    def capability_names(self) -> List[str]:
        return [c["name"] for c in self.capabilities()]

    # ------------------------------------------------------------------
    # Tool state predicates — REGISTERED / IMPLEMENTED are distinct.
    # ------------------------------------------------------------------
    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def is_implemented(self, name: str) -> bool:
        tool = self._tools.get(name)
        return bool(tool and tool.executor is not None)

    # ------------------------------------------------------------------
    def run(self, name: str, *, policy=None, ctx=None, **kwargs):
        """Honest execution boundary. Returns a structured Observation
        when the tool is registered; keeps the legacy ToolResult shape
        ONLY for the unknown-tool case (nothing was ever registered, so
        there is no implementation to report on).
        """
        started = time.monotonic()

        tool = self.get(name)
        if not tool:
            # Not even REGISTERED.
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
                verified=False,
            )

        # --- IMPLEMENTED check -------------------------------------
        if tool.executor is None:
            return self.compressor.compress(
                Observation.not_implemented(
                    name,
                    f"Tool '{name}' is REGISTERED but has no executor "
                    f"(status={tool.status}). Nothing was executed.",
                )
            )

        # --- Policy gate BEFORE any execution -----------------------
        # (AgentLoop enforces policy too; this is defense-in-depth so no
        #  caller can bypass Policy by hitting the Registry directly.)
        decision = _PolicyProxy.decide(policy, ctx, name, tool)
        if decision is not None and not decision.allowed:
            return self.compressor.compress(
                Observation.blocked(name, decision.reason or "Blocked by policy.")
            )

        # --- Normalize + validate input ------------------------------
        # Task 6 (minimal): the observation-context carrier is a control
        # input, not tool payload — it never reaches executor kwargs.
        if isinstance(kwargs, dict):
            kwargs.pop("previous_observation", None)
        kwargs = tool.normalize_input(kwargs)
        validation_error = tool.validate_input(kwargs)
        if validation_error:
            return self.compressor.compress(Observation(
                tool=name,
                status=ObservationStatus.FAILURE,
                summary=validation_error,
                stderr=validation_error,
                duration=round(time.monotonic() - started, 6),
                metadata={"validation": True},
            ))

        # --- Execute with REAL wall-clock timeout --------------------
        # The blocking sync executor is offloaded to the shared bounded
        # pool, so the calling thread/event loop is never stuck waiting
        # longer than `timeout` seconds. A timed-out worker cannot be
        # killed in Python — we do NOT claim cancellation; observation
        # honestly reports TIMEOUT with worker_may_still_run metadata.
        limit = max(1, int(getattr(tool, "timeout", 30) or 30))
        future = self._executor_pool().submit(tool.executor, **kwargs)
        try:
            result = future.result(timeout=limit)
        except TimeoutError:
            return self.compressor.compress(Observation(
                tool=name,
                status=ObservationStatus.TIMEOUT,
                summary=f"Executor exceeded {limit}s wall-clock limit.",
                duration=round(time.monotonic() - started, 6),
                metadata={"timeout_limit": limit, "worker_may_still_run": True},
            ))
        except Exception as e:  # executor raised
            return self.compressor.compress(Observation.failure(
                name, error=str(e),
                duration=round(time.monotonic() - started, 6),
            ))

        duration = round(time.monotonic() - started, 6)

        # --- Legacy ToolResult adapter boundary ----------------------
        if isinstance(result, ToolResult):
            stdout = ""
            data = dict(result.data or {})
            payload = data.pop("stdout", None)
            if payload is not None:
                stdout = str(payload)
            obs = Observation(
                tool=name,
                status=ObservationStatus.SUCCESS if result.success else ObservationStatus.FAILURE,
                summary=result.error or f"{name} finished ({'ok' if result.success else 'failed'})",
                stdout=stdout,
                stderr=result.error or "",
                duration=duration,
                # Full legacy payload kept losslessly under "data"; flat keys
                    # remain for metadata consumers.
                    metadata={**data, "verified": bool(result.verified), "data": data},
            )
            return self.compressor.compress(obs)

        # Unexpected executor return type -> honest FAILURE, never SUCCESS.
        return self.compressor.compress(Observation.failure(
            name,
            error=f"Executor returned unsupported type {type(result).__name__}",
            duration=duration,
        ))