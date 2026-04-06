"""Helpers for safe edit orchestration and structured code edit promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from impliforge.agents.base import AgentResult
from impliforge.orchestration.artifact_writer import WorkflowArtifactWriter
from impliforge.orchestration.workflow import WorkflowState
from impliforge.runtime.code_editing import (
    CodeEditKind,
    CodeEditRequest,
    CodeEditRiskFlag,
    StructuredCodeEditor,
    proposal_consumability_is_structured,
)
from impliforge.runtime.code_editing import (
    proposal_policy_requires_explicit_approval as code_policy_requires_explicit_approval,
)
from impliforge.runtime.editor import (
    EditOperationKind,
    EditRequest,
    SafeEditor,
)
from impliforge.runtime.editor import (
    proposal_policy_requires_explicit_approval as file_policy_requires_explicit_approval,
)


class EditPhaseOrchestrator:
    """Coordinate safe edit and structured code edit phases."""

    def __init__(
        self,
        *,
        safe_editor: SafeEditor,
        code_editor: StructuredCodeEditor,
        artifact_writer: WorkflowArtifactWriter,
    ) -> None:
        self.safe_editor = safe_editor
        self.code_editor = code_editor
        self.artifact_writer = artifact_writer

    def apply_safe_edit_phase(
        self,
        *,
        state: WorkflowState,
        requirement: str,
        requirements_result: AgentResult,
        planning_result: AgentResult,
        documentation_result: AgentResult,
        implementation_result: AgentResult,
        test_design_result: AgentResult,
        test_execution_result: AgentResult,
        review_result: AgentResult,
        fix_result: AgentResult | None,
    ) -> None:
        """Apply allowlisted file edits and structured source edits."""
        operations = self.build_safe_edit_operations(
            state=state,
            requirement=requirement,
            requirements_result=requirements_result,
            planning_result=planning_result,
            documentation_result=documentation_result,
            implementation_result=implementation_result,
            test_design_result=test_design_result,
            test_execution_result=test_execution_result,
            review_result=review_result,
            fix_result=fix_result,
        )

        if not operations:
            state.add_note("safe edit phase で適用対象はなかった。")
            return

        results = self.safe_editor.apply_many(operations)
        applied_paths: list[str] = []
        denied_paths: list[str] = []
        safe_edit_results: list[dict[str, Any]] = []

        for request, result in zip(operations, results, strict=False):
            safe_edit_results.append(
                {
                    "proposal_id": request.proposal_id,
                    "relative_path": result.relative_path,
                    "operation": request.operation.value,
                    "approval_policy": request.approval_policy,
                    "consumability": request.consumability,
                    "ok": result.ok,
                    "changed": result.changed,
                    "message": result.message,
                }
            )
            if result.ok and result.changed:
                self._record_path(state, result.relative_path, applied_paths)
            elif not result.ok:
                denied_paths.append(f"{result.relative_path}: {result.message}")

        if safe_edit_results:
            state.merge_task_outputs(
                "implementation",
                {
                    "safe_edit_results": safe_edit_results,
                    "safe_edit_summary": {
                        "request_count": len(safe_edit_results),
                        "applied_count": len(applied_paths),
                        "denied_count": len(denied_paths),
                        "applied_paths": list(applied_paths),
                        "denied_paths": list(denied_paths),
                    },
                },
            )
            state.add_artifact(
                f"artifacts/workflows/{state.workflow_id}/safe-edit-results.json"
            )

        structured_edit_paths, structured_denied_paths = (
            self.apply_structured_code_edit_phase(
                state=state,
                implementation_result=implementation_result,
                fix_result=fix_result,
            )
        )
        for path in structured_edit_paths:
            self._record_path(state, path, applied_paths)
        denied_paths.extend(structured_denied_paths)

        if applied_paths:
            state.add_note(
                f"safe edit phase で {len(applied_paths)} 件の allowlist 対象ファイルを更新した。"
            )
        else:
            state.add_note("safe edit phase で更新されたファイルはなかった。")

        if denied_paths:
            state.add_note(
                "safe edit phase で承認または allowlist により拒否された対象がある: "
                + " | ".join(denied_paths)
            )

    def build_safe_edit_operations(
        self,
        *,
        state: WorkflowState,
        requirement: str,
        requirements_result: AgentResult,
        planning_result: AgentResult,
        documentation_result: AgentResult,
        implementation_result: AgentResult,
        test_design_result: AgentResult,
        test_execution_result: AgentResult,
        review_result: AgentResult,
        fix_result: AgentResult | None,
    ) -> list[EditRequest]:
        """Build allowlisted file edit requests for docs and artifacts."""
        operations: list[EditRequest] = []

        design_document = documentation_result.outputs.get("design_document")
        if isinstance(design_document, str) and design_document.strip():
            operations.append(
                EditRequest(
                    relative_path="docs/design.md",
                    operation=EditOperationKind.WRITE,
                    content=design_document,
                    reason="Persist generated design document through safe edit phase",
                )
            )

        runbook_document = documentation_result.outputs.get("runbook_document")
        if isinstance(runbook_document, str) and runbook_document.strip():
            operations.append(
                EditRequest(
                    relative_path="docs/runbook.md",
                    operation=EditOperationKind.WRITE,
                    content=runbook_document,
                    reason="Persist generated runbook through safe edit phase",
                )
            )

        test_plan_document = test_design_result.outputs.get("test_plan_document")
        if isinstance(test_plan_document, str) and test_plan_document.strip():
            operations.append(
                EditRequest(
                    relative_path="docs/test-plan.md",
                    operation=EditOperationKind.WRITE,
                    content=test_plan_document,
                    reason="Persist generated test plan through safe edit phase",
                )
            )

        test_results_document = test_execution_result.outputs.get(
            "test_results_document"
        )
        if isinstance(test_results_document, str) and test_results_document.strip():
            operations.append(
                EditRequest(
                    relative_path="docs/test-results.md",
                    operation=EditOperationKind.WRITE,
                    content=test_results_document,
                    reason="Persist generated test results through safe edit phase",
                )
            )

        review_report = review_result.outputs.get("review_report")
        if isinstance(review_report, str) and review_report.strip():
            operations.append(
                EditRequest(
                    relative_path="docs/review-report.md",
                    operation=EditOperationKind.WRITE,
                    content=review_report,
                    reason="Persist generated review report through safe edit phase",
                )
            )

        if fix_result is not None:
            fix_report = fix_result.outputs.get("fix_report")
            if isinstance(fix_report, str) and fix_report.strip():
                operations.append(
                    EditRequest(
                        relative_path="docs/fix-report.md",
                        operation=EditOperationKind.WRITE,
                        content=fix_report,
                        reason="Persist generated fix report through safe edit phase",
                    )
                )

        final_summary = self.artifact_writer.build_final_summary(
            state=state,
            requirement=requirement,
            implementation_result=implementation_result,
            test_design_result=test_design_result,
            test_execution_result=test_execution_result,
            review_result=review_result,
            fix_result=fix_result,
        )
        operations.append(
            EditRequest(
                relative_path="docs/final-summary.md",
                operation=EditOperationKind.WRITE,
                content=final_summary,
                reason="Persist final summary through safe edit phase",
            )
        )

        operations.append(
            EditRequest(
                relative_path=f"artifacts/workflows/{state.workflow_id}/workflow-details.json",
                operation=EditOperationKind.WRITE,
                content=self.artifact_writer.json_text(
                    {
                        "workflow": state.to_dict(),
                        "requirements_result": self.artifact_writer.result_to_dict(
                            requirements_result
                        ),
                        "planning_result": self.artifact_writer.result_to_dict(
                            planning_result
                        ),
                        "documentation_result": self.artifact_writer.result_to_dict(
                            documentation_result
                        ),
                        "implementation_result": self.artifact_writer.result_to_dict(
                            implementation_result
                        ),
                        "test_design_result": self.artifact_writer.result_to_dict(
                            test_design_result
                        ),
                        "test_execution_result": self.artifact_writer.result_to_dict(
                            test_execution_result
                        ),
                        "review_result": self.artifact_writer.result_to_dict(
                            review_result
                        ),
                        "fix_result": self.artifact_writer.result_to_dict(fix_result)
                        if fix_result
                        else None,
                    }
                ),
                reason="Persist workflow details through safe edit phase",
            )
        )

        return operations

    def apply_structured_code_edit_phase(
        self,
        *,
        state: WorkflowState,
        implementation_result: AgentResult,
        fix_result: AgentResult | None,
    ) -> tuple[list[str], list[str]]:
        """Apply structured source edits under the current workspace `src/` and `tests/` roots."""
        implementation = implementation_result.outputs.get("implementation", {})
        if not isinstance(implementation, dict):
            return [], []

        applied_paths: list[str] = []
        denied_paths: list[str] = []
        requests = self.build_structured_code_edit_requests(implementation)

        if fix_result is not None:
            fix_plan = fix_result.outputs.get("fix_plan", {})
            if isinstance(fix_plan, dict):
                requests.extend(self.build_structured_fix_code_edit_requests(fix_plan))

        execution_results: list[dict[str, Any]] = []
        for request in requests:
            result = self.code_editor.apply(request)
            execution_results.append(
                {
                    "proposal_id": request.proposal_id,
                    "relative_path": request.relative_path,
                    "kind": request.kind.value,
                    "approval_policy": request.approval_policy,
                    "consumability": request.consumability,
                    "ok": result.ok,
                    "changed": result.changed,
                    "message": getattr(result, "message", ""),
                }
            )
            if (
                result.ok
                and result.changed
                and request.relative_path not in applied_paths
            ):
                applied_paths.append(request.relative_path)
            elif not result.ok:
                message = (
                    getattr(result, "message", "") or "structured code edit denied"
                )
                denied_paths.append(f"{request.relative_path}: {message}")

        if execution_results:
            state.merge_task_outputs(
                "implementation",
                {
                    "structured_code_edit_results": execution_results,
                    "structured_code_edit_summary": {
                        "request_count": len(execution_results),
                        "applied_count": len(applied_paths),
                        "denied_count": len(denied_paths),
                        "applied_paths": list(applied_paths),
                        "denied_paths": list(denied_paths),
                    },
                },
            )
            state.add_artifact(
                f"artifacts/workflows/{state.workflow_id}/structured-code-edit-results.json"
            )

        if applied_paths:
            state.add_note(
                "structured code edit phase で current workspace の src/ または tests/ 配下の更新を適用した。"
            )

        return applied_paths, denied_paths

    def build_structured_code_edit_requests(
        self,
        implementation: dict[str, Any],
    ) -> list[CodeEditRequest]:
        """Build structured code edit requests from implementation proposals."""
        requests: list[CodeEditRequest] = []
        edit_proposals = implementation.get("edit_proposals", [])
        if not isinstance(edit_proposals, list):
            return requests

        for item in edit_proposals:
            requests.extend(self.code_edit_requests_from_proposal(item))
        return requests

    def build_structured_fix_code_edit_requests(
        self,
        fix_plan: dict[str, Any],
    ) -> list[CodeEditRequest]:
        """Build structured code edit requests from fix proposals."""
        requests: list[CodeEditRequest] = []
        edit_proposals = fix_plan.get("edit_proposals", [])
        if not isinstance(edit_proposals, list):
            return requests

        for item in edit_proposals:
            requests.extend(self.code_edit_requests_from_proposal(item))
        return requests

    def code_edit_requests_from_proposal(
        self,
        proposal: Any,
    ) -> list[CodeEditRequest]:
        """Convert a proposal payload into structured code edit requests."""
        normalized = self._normalize_edit_proposal(proposal)
        if normalized is None:
            return []

        reason = (
            " | ".join(normalized["instructions"])
            or normalized["summary"]
            or "Apply structured code edit proposal"
        )
        risk_flags = self._extract_code_edit_risk_flags(normalized)

        requests: list[CodeEditRequest] = []
        for target_path in normalized["targets"]:
            if not (
                target_path == "src"
                or target_path.startswith("src/")
                or target_path == "tests"
                or target_path.startswith("tests/")
            ):
                continue

            for edit in normalized["edits"]:
                request = self.code_edit_request_from_edit(
                    target_path=target_path,
                    edit=edit,
                    reason=reason,
                    risk_flags=risk_flags,
                    proposal_id=normalized["proposal_id"],
                    approval_policy=normalized["approval_policy"],
                    consumability=normalized["consumability"],
                )
                if request is not None:
                    requests.append(request)

        return requests

    def code_edit_request_from_edit(
        self,
        *,
        target_path: str,
        edit: Any,
        reason: str,
        risk_flags: tuple[CodeEditRiskFlag, ...] = (),
        proposal_id: str = "",
        approval_policy: str = "",
        consumability: str = "",
    ) -> CodeEditRequest | None:
        """Convert a single edit payload into a structured code edit request."""
        if not isinstance(edit, dict):
            return None

        edit_kind = str(edit.get("edit_kind", "")).strip()
        target_symbol = str(edit.get("target_symbol", "")).strip()
        intent = str(edit.get("intent", "")).strip()
        request_reason = intent or reason or "Apply structured code edit proposal"

        if edit_kind == "replace_block":
            if not target_symbol:
                return None

            begin_marker = f"# BEGIN STRUCTURED EDIT: {target_symbol}"
            end_marker = f"# END STRUCTURED EDIT: {target_symbol}"
            content = self.build_structured_replacement_content(
                target_path=target_path,
                target_symbol=target_symbol,
                request_reason=request_reason,
            )

            return CodeEditRequest(
                relative_path=target_path,
                kind=CodeEditKind.REPLACE_MARKED_BLOCK,
                reason=request_reason,
                risk_flags=risk_flags,
                proposal_id=proposal_id,
                approval_policy=approval_policy,
                consumability=consumability,
                begin_marker=begin_marker,
                end_marker=end_marker,
                content=content,
            )

        if edit_kind == "ensure_snippet":
            content = self.build_structured_replacement_content(
                target_path=target_path,
                target_symbol=target_symbol,
                request_reason=request_reason,
            )

            return CodeEditRequest(
                relative_path=target_path,
                kind=CodeEditKind.ENSURE_SNIPPET,
                reason=request_reason,
                risk_flags=risk_flags,
                proposal_id=proposal_id,
                approval_policy=approval_policy,
                consumability=consumability,
                content=content,
            )

        return None

    def _extract_code_edit_risk_flags(
        self,
        proposal: Any,
    ) -> tuple[CodeEditRiskFlag, ...]:
        """Extract structured risk flags from a proposal payload."""
        if not isinstance(proposal, dict):
            return ()

        raw_flags = proposal.get("risk_flags", [])
        if not isinstance(raw_flags, list):
            return ()

        normalized_flags: list[CodeEditRiskFlag] = []
        for item in raw_flags:
            value = str(item).strip()
            if not value:
                continue
            try:
                flag = CodeEditRiskFlag(value)
            except ValueError:
                continue
            if flag not in normalized_flags:
                normalized_flags.append(flag)

        return tuple(normalized_flags)

    def _normalize_edit_proposal(
        self,
        proposal: Any,
    ) -> dict[str, Any] | None:
        """Validate and normalize a structured edit proposal."""
        if not isinstance(proposal, dict):
            return None

        proposal_id = str(proposal.get("proposal_id", "")).strip()
        summary = str(proposal.get("summary", "")).strip()
        approval_policy = str(proposal.get("approval_policy", "")).strip()
        consumability = str(proposal.get("consumability", "")).strip()

        targets = proposal.get("targets", [])
        instructions = proposal.get("instructions", [])
        edits = proposal.get("edits", [])

        if not proposal_id or not summary:
            return None
        if not isinstance(targets, list) or not isinstance(instructions, list):
            return None
        if not isinstance(edits, list) or not edits:
            return None
        if not approval_policy or not consumability:
            return None
        if not proposal.get("safe_edit_ready", False):
            return None
        if not proposal_consumability_is_structured(consumability):
            return None
        if not code_policy_requires_explicit_approval(approval_policy):
            return None
        if not file_policy_requires_explicit_approval(approval_policy):
            return None

        normalized_targets = [
            str(item).strip() for item in targets if str(item).strip()
        ]
        normalized_instructions = [
            str(item).strip() for item in instructions if str(item).strip()
        ]
        normalized_edits = [item for item in edits if isinstance(item, dict)]

        if not normalized_targets or not normalized_edits:
            return None

        return {
            "proposal_id": proposal_id,
            "summary": summary,
            "targets": normalized_targets,
            "instructions": normalized_instructions,
            "edits": normalized_edits,
            "approval_policy": approval_policy,
            "consumability": consumability,
            "risk_flags": proposal.get("risk_flags", []),
        }

    def build_structured_replacement_content(
        self,
        *,
        target_path: str,
        target_symbol: str,
        request_reason: str,
    ) -> str:
        """Return generic placeholder content for workspace structured edits."""
        placeholder_lines = [
            "# Generated by impliforge structured edit phase.",
            f"# Target path: {target_path}",
            f"# Edit intent: {request_reason}",
        ]
        if target_symbol:
            placeholder_lines.append(f"# Target symbol: {target_symbol}")
        placeholder_lines.extend(
            [
                "",
                "raise NotImplementedError(",
                '    "Generated placeholder content requires concrete implementation."',
                ")",
            ]
        )
        return "\n".join(placeholder_lines)

    def _record_path(
        self,
        state: WorkflowState,
        path: str,
        applied_paths: list[str],
    ) -> None:
        normalized = Path(path).as_posix()
        if normalized not in applied_paths:
            applied_paths.append(normalized)
        state.add_artifact(normalized)
        state.add_changed_file(normalized)
