"""Runtime support helpers for approval policy and session rotation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from devagents.orchestration.state_store import StateStore
from devagents.orchestration.workflow import WorkflowState
from devagents.runtime.editor import (
    ApprovalDecision,
    ApprovalResult,
    EditOperationKind,
    EditRequest,
    approve_docs_and_artifacts_only,
)


class SessionManagerLike(Protocol):
    """Protocol for the subset of session manager behavior used here."""

    def rotate_session(
        self,
        state: WorkflowState,
        *,
        token_usage_ratio: float,
        next_action: str,
        last_checkpoint: str,
        persistent_context: dict[str, Any],
    ) -> tuple[Any, Any]:
        """Rotate the current session when thresholds require it."""


@dataclass(slots=True)
class RuntimeSupport:
    """Shared runtime helpers extracted from the main orchestrator."""

    state_store: StateStore
    session_manager: SessionManagerLike

    def rotate_session_if_needed(
        self,
        state: WorkflowState,
        *,
        token_usage_ratio: float,
        next_action: str,
        last_checkpoint: str,
        persistent_context: dict[str, Any],
    ) -> None:
        """Rotate the session and persist the pre-rotation snapshot when needed."""
        decision, snapshot = self.session_manager.rotate_session(
            state,
            token_usage_ratio=token_usage_ratio,
            next_action=next_action,
            last_checkpoint=last_checkpoint,
            persistent_context=persistent_context,
        )
        if not getattr(decision, "should_rotate", False):
            return

        previous_session_id = snapshot.session_id
        previous_snapshot_path = self.state_store.save_session_snapshot(snapshot)
        state.add_note(
            "mid-run session rotation を実行し、後続フェーズを新 session で継続する。"
        )
        state.add_artifact(previous_snapshot_path.as_posix())
        state.add_note(
            f"pre-rotation session snapshot を保存した: {previous_session_id}"
        )

    def approval_hook(
        self,
        request: EditRequest,
        absolute_path: Path,
    ) -> ApprovalResult:
        """Apply the repository approval policy for safe editor requests."""
        relative_path = request.normalized_relative_path()

        if relative_path.startswith("docs/") or relative_path.startswith("artifacts/"):
            return approve_docs_and_artifacts_only(request, absolute_path)

        if relative_path.startswith("src/devagents/"):
            if request.operation == EditOperationKind.DELETE:
                return ApprovalResult(
                    decision=ApprovalDecision.DENIED,
                    reason="delete operations under src/devagents are not allowed",
                )

            if request.operation in {
                EditOperationKind.WRITE,
                EditOperationKind.APPEND,
            }:
                return ApprovalResult(
                    decision=ApprovalDecision.APPROVED,
                    reason="src/devagents allowlist permits controlled edits",
                )

        return ApprovalResult(
            decision=ApprovalDecision.DENIED,
            reason="target is outside configured approval scope",
        )
