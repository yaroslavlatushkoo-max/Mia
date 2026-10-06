from __future__ import annotations

"""ObservationCompressor (Task 5).

Deterministic, pure, LLM-free compression of Observation stdout/stderr so
huge outputs never flood ExecutionTrace / LLM context unbounded.

Rules:
  * short output            -> unchanged;
  * long output             -> HEAD + explicit truncation marker + TAIL;
  * errors are NEVER lost   -> stderr is always preserved in full when it
                               is non-empty and fits the error budget; if
                               even that must be truncated, the marker
                               keeps the FIRST lines (the exception itself)
                               AND the LAST lines (the traceback end);
  * same input              -> byte-identical output (no randomness, no
                               time dependence).
"""

from typing import Optional, Tuple

from .observation import Observation


class ObservationCompressor:
    """Head/tail compression with a deterministic truncation marker."""

    DEFAULT_MAX_CHARS = 4000        # per stream (stdout/stderr)
    DEFAULT_MARKER = "\n[... {omitted} chars omitted ...]\n"

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS):
        if max_chars < 16:
            raise ValueError("max_chars too small to preserve head+tail meaningfully")
        self.max_chars = max_chars

    # ------------------------------------------------------------------
    def compress_stream(self, text: str) -> Tuple[str, bool]:
        """Return (compressed_text, was_truncated). Deterministic."""
        if not text or len(text) <= self.max_chars:
            return text, False

        keep_each = max(1, (self.max_chars - len(self.DEFAULT_MARKER)) // 2)
        head = text[:keep_each]
        tail = text[-keep_each:]
        omitted = len(text) - len(head) - len(tail)
        marker = self.DEFAULT_MARKER.format(omitted=omitted)
        return head + marker + tail, True

    # ------------------------------------------------------------------
    def compress(self, obs: Observation) -> Observation:
        """Return a NEW compressed Observation; input is not mutated."""
        stdout, out_trunc = self.compress_stream(obs.stdout)
        stderr, err_trunc = self.compress_stream(obs.stderr)

        metadata = dict(obs.metadata)
        flags = []
        if out_trunc:
            flags.append("stdout")
        if err_trunc:
            flags.append("stderr")
        if flags:
            metadata["compressed_streams"] = flags
            # Preserve the error summary even if stderr got truncated —
            # the diagnostic headline must survive compression.
            if err_trunc and obs.summary:
                metadata.setdefault("error_summary", obs.summary[:512])

        return Observation(
            tool=obs.tool,
            status=obs.status,
            summary=obs.summary,          # summary/status never compressed away
            stdout=stdout,
            stderr=stderr,
            duration=obs.duration,
            metadata=metadata,
        )
