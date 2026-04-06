# devagents

`devagents` は、GitHub Copilot SDK を基盤にした orchestrator-centric なマルチエージェント実行ツール。

要件分析、計画、ドキュメント生成、実装提案、テスト設計・実行、レビュー、修正ループ、成果物保存までを一連の workflow として扱う。

## License

This project is licensed under the MIT License. See `LICENSE` for details.

## Features

- requirements / planning / documentation / implementation / test_design / test_execution / review / fix loop を持つ workflow
- session snapshot / restore / rotation
- task-aware model routing
- operator-facing run summary / final summary / review / fix artifacts
- acceptance gating と completion evidence
- approval-aware safe edit orchestration

## Installation

依存解決と実行は `uv` 前提。

```sh
uv sync
```

テスト依存も入れる場合:

```sh
uv sync --extra test
```

## CLI Usage

`devagents` は**要件文字列そのものではなく、要件を書いたファイルパス**を位置引数として受け取る。

### Basic

```sh
uv run devagents requirements/sample-requirement.md
```

または module 実行:

```sh
uv run python -m devagents requirements/sample-requirement.md
```

### With options

```sh
uv run devagents requirements/sample-requirement.md \
  --model gpt-5.4 \
  --routing-mode quality \
  --token-usage-ratio 0.35 \
  --artifacts-dir artifacts \
  --docs-dir docs
```

## Requirement File Format

要件ファイルは plain text / markdown を想定。複数行で書いてよい。

例:

```md
GitHub Copilot SDK を用いたマルチエージェント環境を構築する

- session persistence を持つこと
- review と fix loop を含むこと
- docs/ と artifacts/ に成果物を保存すること
```

## Error Handling

次の場合はエラー終了する。

- 指定した要件ファイルが存在しない
- 要件ファイルが空
- 要件ファイルを読み取れない

例:

```sh
uv run devagents requirements/missing.md
# error: requirement file not found: requirements/missing.md
```

## Generated Outputs

主に以下を生成する。

### docs

- `docs/design.md`
- `docs/runbook.md`
- `docs/test-plan.md`
- `docs/test-results.md`
- `docs/review-report.md`
- `docs/fix-report.md`
- `docs/final-summary.md`

### artifacts

- `artifacts/workflow-state.json`
- `artifacts/sessions/<session_id>/session-snapshot.json`
- `artifacts/workflows/<workflow_id>/workflow-details.json`
- `artifacts/summaries/<workflow_id>/run-summary.json`

## Validation

全体テスト:

```sh
uv run pytest -q tests
```

coverage:

```sh
uv run pytest --cov=src/devagents --cov-report=term-missing:skip-covered -q tests
```

## Notes

- `docs/` と `artifacts/` への生成物保存は通常運用として扱う
- source edit は approval-aware な経路を通す前提
- unresolved open questions は resolved または explicitly deferred として扱う