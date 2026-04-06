# 並列実装計画

## 目的

既存の `implementation-plan.md` を踏まえ、追加済みの「ソース実装」「テスト実装」機能を実運用レベルまで前進させるための、`5` 並列前提の実装計画を定義する。

この計画の狙いは次の 3 点。

1. `src/impliforge/` 配下の実装機能を、提案生成中心から実行可能な統合フローへ進める
2. `tests/` 配下の検証を、個別ユニット中心から並列実装後の回帰安全網へ拡張する
3. 並列実装しても競合しにくいように、担当スコープ・依存関係・完了条件を明確化する

---

## 現状整理

現状のコードベースから見える前提は以下。

- オーケストレーションの骨格は存在する
- `requirements` / `planning` / `documentation` / `implementation` / `test_design` / `test_execution` / `review` / `fixer` の各エージェントは概ね揃っている
- `WorkflowState` とタスク依存関係は定義済み
- `main.py` 側には段階実行、fix loop、artifact 出力、safe edit phase の流れがある
- `runtime/editor.py` と `runtime/code_editing.py` に安全な編集の基盤がある
- テストは広く存在するが、追加実装を前提にした責務分離・統合保証・回帰観点の強化余地がある

つまり、完全な新規実装ではなく、**既存骨格を壊さずに、実装機能とテスト機能を一段深く統合するフェーズ**とみなす。

---

## 今回の実装方針

### 方針 1: 小さい変更を 5 本に分割する

並列化のため、変更を以下の 5 ストリームに分ける。

1. オーケストレーター統合強化
2. 実装提案から安全編集への橋渡し強化
3. テスト設計・テスト実行の出力品質強化
4. 成果物・ドキュメント出力の整合強化
5. テスト拡充と回帰安全網の追加

### 方針 2: 書き込み競合を減らす

各ストリームは、できるだけ別ファイル群を主担当にする。  
完全に独立できない箇所は `main.py` と一部共有モジュールに集中するため、そこは最後に薄く統合する。

### 方針 3: 先に契約を固める

並列実装で壊れやすいのは、各フェーズ間の `outputs` 形状と artifact 名。  
そのため、まず以下を契約として固定する。

- `implementation.outputs["implementation"]`
- `test_design.outputs["test_plan"]`
- `test_execution.outputs["test_results"]`
- `review.outputs["review"]`
- `fixer.outputs["fix_report"]` または fix 系出力
- `docs/*.md` と `artifacts/*` の保存先・命名

---

## 5 並列の担当計画

## Stream 1: オーケストレーター統合強化

### 目的

各エージェントの出力を `main.py` と orchestration 層で一貫して受け渡し、fix loop・finalization・state 更新の整合を高める。

### 主担当ファイル

- `src/impliforge/main.py`
- `src/impliforge/orchestration/orchestrator.py`
- `src/impliforge/orchestration/workflow.py`

### 実装内容

- 各 phase の `inputs` / `outputs` 契約を明文化して受け渡しを安定化
- `implementation` → `test_design` → `test_execution` → `review` の依存データを整理
- fix loop 後の再実行結果のマージ規則を明確化
- `WorkflowState` の note / risk / open question / changed file 反映を統一
- finalization 判定の条件を追加実装後の実態に合わせて調整
- phase 完了イベントの記録粒度を揃える

### 完了条件

- 各 phase の成功時に state が期待どおり更新される
- fix loop 後の再実行結果が欠落なく最終 state に反映される
- finalization の blocked / completed 条件がテストで保証される

### リスク

- `main.py` に責務が集中しているため差分が大きくなりやすい
- 既存テストの期待値と新しい state 反映ルールが衝突しやすい

---

## Stream 2: 実装提案から安全編集への橋渡し強化

### 目的

`ImplementationAgent` が生成する提案を、単なる説明文ではなく、安全編集ランタイムが扱いやすい構造化データへ寄せる。

### 主担当ファイル

- `src/impliforge/agents/implementation.py`
- `src/impliforge/runtime/editor.py`
- `src/impliforge/runtime/code_editing.py`
- 必要に応じて `src/impliforge/orchestration/edit_phase.py`

### 実装内容

- `edit_proposals` の schema を整理
- `proposal_id` / `targets` / `instructions` / `edits` の必須性を揃える
- 構造化編集要求と approval policy の対応を明確化
- `src/impliforge/` 向け編集と `docs/` / `artifacts/` 向け編集の扱いを分離
- broad rewrite や危険フラグの deny 条件をテストしやすい形に整理
- safe edit phase が proposal を解釈しやすい中間表現を追加

### 完了条件

- `ImplementationAgent` の出力だけで safe edit phase が必要情報を取得できる
- 承認不要の安全編集と、明示承認が必要な編集が区別される
- 構造化編集の deny / approve 条件がテストで固定される

### リスク

- 提案 schema を変えると downstream テストが広く壊れる
- 実編集まで踏み込みすぎると安全性ルールとの整合が崩れる

---

## Stream 3: テスト設計・テスト実行の出力品質強化

### 目的

`test_design` と `test_execution` を、単なる補助フェーズではなく、レビューと fix loop の判断材料として十分な品質にする。

### 主担当ファイル

- `src/impliforge/agents/test_design.py`
- `src/impliforge/agents/test_execution.py`
- 必要に応じて `src/impliforge/agents/reviewer.py`

### 実装内容

- `test_plan` の構造を安定化
- acceptance criteria と test case の対応を明示
- code change slice ごとの検証観点を強化
- `test_results` に executed checks / provisional status / unresolved concerns を揃える
- review が test outputs を読みやすいよう summary 項目を追加
- open questions が test plan / test results / review にどう伝播するかを統一

### 完了条件

- `test_design` の出力だけで主要な検証観点が追える
- `test_execution` の出力だけで review が blocking issue を判断できる
- open questions と acceptance coverage が各 phase で欠落しない

### リスク

- 出力を増やしすぎると既存テストの期待値更新が大きくなる
- review 側のロジックと二重管理になりやすい

---

## Stream 4: 成果物・ドキュメント出力の整合強化

### 目的

`docs/` と `artifacts/` に保存される成果物を、phase ごとに一貫した命名・内容・参照関係に揃える。

### 主担当ファイル

- `src/impliforge/orchestration/artifact_writer.py`
- `src/impliforge/agents/documentation.py`
- `docs/` 配下の生成対象に関わる処理
- 必要に応じて `src/impliforge/main.py`

### 実装内容

- `design.md` / `runbook.md` / `test-plan.md` / `test-results.md` / `review-report.md` / `fix-report.md` / `final-summary.md` の出力条件を整理
- phase 成功時のみ保存するもの、常に保存するものを分離
- artifact writer の責務を「保存」と「state 反映」で明確化
- workflow details / run summary の JSON 出力内容を揃える
- changed files / artifacts / notes の相互参照を改善
- docs 出力の見出し構成を安定化

### 完了条件

- 各 phase の成功時に期待するドキュメントが保存される
- JSON artifact と Markdown artifact の内容が矛盾しない
- state.artifacts と実ファイル出力の対応がテストで保証される

### リスク

- 出力ファイル名変更が既存テストに広く影響する
- `main.py` と writer の責務境界が曖昧だと重複保存が起きる

---

## Stream 5: テスト拡充と回帰安全網の追加

### 目的

上記 4 ストリームの変更を安全に進めるため、ユニットテスト・統合テスト・回帰テストを追加する。

### 主担当ファイル

- `tests/test_main_orchestrator.py`
- `tests/test_orchestration_orchestrator.py`
- `tests/test_orchestration_workflow.py` 相当の既存対象
- `tests/test_agents_implementation.py`
- `tests/test_agents_test_design.py`
- `tests/test_agents_test_execution.py`
- `tests/test_agents_reviewer.py`
- `tests/test_runtime_code_editing.py`
- `tests/test_runtime_editor.py`

### 実装内容

- phase 間の output contract を固定するテスト追加
- fix loop の再実行マージを検証するテスト追加
- safe edit proposal の approve / deny 条件テスト追加
- artifact 保存と state.artifacts の整合テスト追加
- open questions が finalization を block する回帰テスト追加
- changed files / risks / notes の反映テスト追加

### 完了条件

- 追加した契約がテストで固定される
- 並列実装した 4 ストリームの主要変更点に回帰テストがある
- 失敗時の原因が phase 単位で追いやすい

### リスク

- テストが実装詳細に寄りすぎると変更耐性が落ちる
- 期待値更新だけの作業になり、本質的な契約保証が弱くなる

---

## 実装順序

5 並列とはいえ、完全同時ではなく依存を意識して進める。

### Wave 1

- Stream 2: 実装提案 schema の整理
- Stream 3: test plan / test results schema の整理
- Stream 4: artifact 出力契約の整理
- Stream 5: 契約テストの先行追加
- Stream 1: orchestrator 側の受け口整理

### Wave 2

- Stream 1: phase 統合と fix loop マージ実装
- Stream 2: safe edit bridge 実装
- Stream 3: review 連携強化
- Stream 4: docs / artifacts 保存処理の統合
- Stream 5: 統合テスト拡充

### Wave 3

- 全体の期待値調整
- 回帰テスト修正
- 不要な重複ロジックの整理
- 最終ドキュメント更新

---

## 依存関係

### 強い依存

- Stream 1 は Stream 2, 3, 4 の output contract に依存する
- Stream 5 は全ストリームに追従するが、契約テストは先行可能

### 弱い依存

- Stream 2 と Stream 3 はほぼ独立
- Stream 4 は artifact 名が固まれば先行可能
- Stream 2 と Stream 4 は safe edit 出力の保存形式で軽く連携する

---

## 変更対象の推奨分担

### 担当 A
- `src/impliforge/agents/implementation.py`
- `src/impliforge/orchestration/edit_phase.py`
- `src/impliforge/runtime/code_editing.py`

### 担当 B
- `src/impliforge/agents/test_design.py`
- `src/impliforge/agents/test_execution.py`
- 必要なら `src/impliforge/agents/reviewer.py`

### 担当 C
- `src/impliforge/orchestration/artifact_writer.py`
- `src/impliforge/agents/documentation.py`

### 担当 D
- `src/impliforge/main.py`
- `src/impliforge/orchestration/orchestrator.py`
- `src/impliforge/orchestration/workflow.py`

### 担当 E
- `tests/` 全般
- ただし各担当が自分の変更に近いテストを先に追加し、最後に E が統合整理する形がよい

---

## 受け入れ条件

以下を満たしたら、この並列実装スライスは完了とみなす。

1. `implementation` の出力が構造化され、safe edit phase で消費可能
2. `test_design` と `test_execution` の出力が review / fix loop の判断材料として十分
3. `docs/` と `artifacts/` の保存結果が state と一致する
4. fix loop 後の rerun 結果が最終 state に正しく反映される
5. open questions / risks / changed files / artifacts の伝播が壊れていない
6. 主要な契約がテストで固定されている

---

## 非ゴール

今回の並列実装では、以下は無理に含めない。

- 大規模なアーキテクチャ再設計
- モデルルーティング戦略の全面刷新
- 外部 API 実行の本格導入
- 危険な自動ソース書き換えの全面解禁
- CLI 仕様の大幅変更

---

## 実装時の注意

- 1 ストリーム 1 目的を守る
- schema 変更時は downstream を同時に確認する
- `main.py` の変更は薄く保つ
- state 更新は `notes` / `risks` / `open_questions` / `changed_files` の重複追加に注意する
- テストは文言一致より構造保証を優先する
- 安全編集は「できることを増やす」より「危険を通さない」を優先する

---

## 最初の具体アクション

1. `implementation` / `test_plan` / `test_results` / `review` の output contract を文書化する
2. 5 ストリームごとに担当ファイルを固定する
3. 契約テストを先に追加する
4. 各ストリームで実装を進める
5. 最後に `main.py` と artifact 出力を統合する
6. 回帰テストを通して差分を収束させる