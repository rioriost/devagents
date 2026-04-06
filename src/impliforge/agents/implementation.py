"""Implementation proposal agent for the impliforge workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from impliforge.agents.base import AgentResult, AgentTask, BaseAgent
from impliforge.agents.proposal_utils import (
    build_structured_edit_proposal,
    normalize_edit_payloads,
)
from impliforge.orchestration.workflow import WorkflowState


class ImplementationAgent(BaseAgent):
    """Create an implementation proposal from the current plan and requirements."""

    agent_name = "implementation"

    async def run(self, task: AgentTask, state: WorkflowState) -> AgentResult:
        # BEGIN STRUCTURED EDIT: ImplementationAgent.run
        normalized_requirements = self._as_dict(
            task.inputs.get("normalized_requirements", {})
        )
        plan = self._as_dict(task.inputs.get("plan", {}))
        copilot_response = str(task.inputs.get("copilot_response", "")).strip()

        objective = str(
            normalized_requirements.get("objective") or state.requirement
        ).strip()
        constraints = self._normalize_list(normalized_requirements.get("constraints"))
        acceptance_criteria = self._normalize_list(
            normalized_requirements.get("acceptance_criteria")
        )
        open_questions = self._normalize_list(
            normalized_requirements.get("open_questions")
        )
        plan_phases = self._normalize_list(plan.get("phases"))
        task_breakdown = self._normalize_task_breakdown(plan.get("task_breakdown"))
        target_source_roots = self._build_target_source_roots()
        structured_edit_targets = self._build_structured_edit_targets(
            target_source_roots,
            objective=objective,
        )

        edit_proposals = [
            self._build_edit_proposal(
                proposal_id="cwd-structured-src-update",
                summary="Promote implementation proposals into generic ensure-snippet payloads for target workspace source files.",
                targets=structured_edit_targets,
                instructions=[
                    "Restrict edits to the current workspace src/ and tests/ roots.",
                    "Require approval for overwrite and delete operations.",
                    "Keep each edit proposal scoped to one behavior change.",
                ],
                edits=[
                    {
                        "edit_kind": "ensure_snippet",
                        "intent": "Add a generated implementation placeholder snippet to the target workspace file.",
                    }
                ],
                approval_policy="cwd_workspace_structured_only",
                safe_edit_scope="src",
                consumability="structured_code_editor",
            ),
        ]

        implementation = {
            "objective": objective,
            "summary": "実装フェーズで着手すべき変更案を整理し、target workspace 向けの generic structured edit proposal を生成した。",
            "strategy": [
                "Keep changes small and align with the existing repository structure",
                "Isolate Copilot SDK integration behind runtime/copilot_client.py",
                "Persist workflow and session state before and after meaningful milestones",
                "Prefer explicit workflow state transitions over implicit behavior",
                "Prefer structured code edits over free-form append-only source mutations",
            ],
            "proposed_modules": [
                {
                    "path": path,
                    "purpose": "Target workspace source or test file selected from the current working directory.",
                }
                for path in structured_edit_targets
            ],
            "code_change_slices": [
                {
                    "slice_id": "workspace-source-update",
                    "goal": "Promote approved implementation proposals into structured source edits under the current workspace src/ and tests/ roots.",
                    "targets": structured_edit_targets,
                    "depends_on": [
                        "planning",
                    ],
                },
                {
                    "slice_id": "artifact-persistence",
                    "goal": "Persist implementation and documentation outputs into docs/ and artifacts/.",
                    "targets": [
                        "docs/design.md",
                        "artifacts/workflows/<workflow_id>/workflow-details.json",
                        "artifacts/summaries/<workflow_id>/run-summary.json",
                    ],
                    "depends_on": [
                        "workspace-source-update",
                    ],
                },
            ],
            "deliverables": [
                "docs/design.md",
                "docs/final-summary.md",
                "artifacts/workflows/<workflow_id>/workflow-details.json",
                "artifacts/summaries/<workflow_id>/run-summary.json",
                "src/**/*.py allowlisted edit proposals",
                "tests/**/*.py allowlisted edit proposals",
            ],
            "acceptance_criteria": acceptance_criteria,
            "constraints": constraints,
            "plan_phases": plan_phases,
            "task_breakdown": task_breakdown,
            "open_questions": open_questions,
            "copilot_response_excerpt": copilot_response[:500]
            if copilot_response
            else "",
            "proposal_schema_version": "2.0",
            "safe_edit_bridge": {
                "structured_editing_ready": True,
                "default_consumability": "structured_code_editor",
                "supported_consumers": [
                    "safe_edit_phase",
                    "structured_code_editor",
                ],
                "approval_policy_map": {
                    "docs_artifacts_only": {
                        "approval_required": True,
                        "allowed_roots": ["docs", "artifacts"],
                        "structured_code_editor_compatible": False,
                    },
                    "cwd_workspace_structured_only": {
                        "approval_required": True,
                        "allowed_roots": target_source_roots,
                        "structured_code_editor_compatible": True,
                    },
                },
            },
            "downstream_handoff": {
                "consumers": [
                    {
                        "phase": "test_design",
                        "inputs": [
                            "implementation.code_change_slices",
                            "implementation.deliverables",
                            "implementation.acceptance_criteria",
                            "implementation.open_questions",
                        ],
                        "purpose": "Generate validation scenarios for proposed change slices and delivery artifacts.",
                    },
                    {
                        "phase": "test_execution",
                        "inputs": [
                            "implementation.code_change_slices",
                            "implementation.edit_proposals",
                            "implementation.constraints",
                        ],
                        "purpose": "Validate executable proposal readiness and confirm proposed targets remain testable.",
                    },
                    {
                        "phase": "review",
                        "inputs": [
                            "implementation.strategy",
                            "implementation.code_change_slices",
                            "implementation.edit_proposals",
                            "implementation.open_questions",
                        ],
                        "purpose": "Assess proposal completeness, risk, and unresolved execution blockers before completion.",
                    },
                    {
                        "phase": "fixer",
                        "inputs": [
                            "implementation.code_change_slices",
                            "implementation.edit_proposals",
                            "implementation.open_questions",
                        ],
                        "purpose": "Reuse implementation proposal structure when generating focused fix slices and revalidation steps.",
                    },
                ],
                "executable_change_proposal_ready": True,
            },
            "edit_proposals": edit_proposals,
        }

        next_actions = [
            "Generate generic ensure-snippet targets from the current workspace src/ and tests/ roots",
            "Persist generated design and implementation proposal artifacts",
            "Extend the workflow into test_design, test_execution, and review phases",
            "Promote generic structured workspace edit proposals into the safe edit phase",
        ]

        risks = [
            "実コード変更前に承認フローが未確定だと、破壊的変更の扱いが曖昧になる",
            "実装提案と既存アーキテクチャの整合確認が不足すると差分が広がる可能性がある",
        ]
        if open_questions:
            risks.append(
                "未解決の open questions が残っているため、実装着手前に確認が必要"
            )

        return AgentResult.success(
            "実装提案を生成し、次のコード変更スライスを整理した。",
            outputs={
                "implementation": implementation,
                "open_questions": open_questions,
            },
            next_actions=next_actions,
            risks=risks,
            metrics={
                "constraint_count": len(constraints),
                "acceptance_criteria_count": len(acceptance_criteria),
                "task_breakdown_count": len(task_breakdown),
                "code_change_slice_count": len(implementation["code_change_slices"]),
                "downstream_consumer_count": len(
                    implementation["downstream_handoff"]["consumers"]
                ),
                "open_question_count": len(open_questions),
                "edit_proposal_count": len(edit_proposals),
            },
        )  # END STRUCTURED EDIT: ImplementationAgent.run

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _build_target_source_roots(self) -> list[str]:
        cwd = Path.cwd()
        roots: list[str] = []

        src_root = cwd / "src"
        tests_root = cwd / "tests"

        if src_root.exists():
            roots.append("src")
        if tests_root.exists():
            roots.append("tests")

        if not roots:
            roots.extend(["src", "tests"])

        return roots

    def _build_structured_edit_targets(
        self,
        roots: list[str],
        *,
        objective: str,
    ) -> list[str]:
        targets: list[str] = []
        package_name = self._infer_package_name(objective)

        for root in roots:
            if root == "src":
                targets.append(f"src/{package_name}/__init__.py")
            elif root == "tests":
                targets.append("tests/test_generated_placeholder.py")

        return targets

    def _infer_package_name(self, objective: str) -> str:
        cwd_name = Path.cwd().name.strip().replace("-", "_")
        if cwd_name:
            return cwd_name

        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", objective.strip().lower())
        normalized = normalized.strip("_")
        if normalized:
            return normalized

        return "app"

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _normalize_task_breakdown(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "")).strip()
            objective = str(item.get("objective", "")).strip()
            depends_on = self._normalize_list(item.get("depends_on"))
            if not task_id and not objective:
                continue
            normalized.append(
                {
                    "task_id": task_id,
                    "objective": objective,
                    "depends_on": depends_on,
                }
            )
        return normalized

    def _build_edit_proposal(
        self,
        *,
        proposal_id: str,
        summary: str,
        targets: list[str],
        instructions: list[str],
        edits: list[dict[str, Any]],
        approval_policy: str,
        safe_edit_scope: str,
        consumability: str,
    ) -> dict[str, Any]:
        return build_structured_edit_proposal(
            proposal_id=proposal_id,
            summary=summary,
            targets=self._normalize_list(targets),
            instructions=self._normalize_list(instructions),
            edits=edits,
            approval_policy=approval_policy,
            safe_edit_scope=safe_edit_scope,
            consumability=consumability,
        )

    def _normalize_edits(self, value: Any) -> list[dict[str, str]]:
        return normalize_edit_payloads(value)
