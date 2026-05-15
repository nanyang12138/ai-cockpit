# AI Cockpit Implementation Plan v0

目标：从 `AI_COCKPIT_SPEC_V1.md` 收敛到一个最小可运行系统。

本计划不做完整平台，不做通用 multi-agent framework，不验证 `ruflo`。第一阶段只做一个可控、可恢复、可验证的 idea-to-MVP execution loop。

## 1. v0.1 核心目标

一句话：

> 用 LangGraph 管流程，用本地 worker 执行代码，用 shell/verifier 检查事实，用 reviewer 判断质量，最后由 manager 决定继续、重试、停止或问人。

v0.1 要跑通这个闭环：

```text
idea input
-> load project/user context
-> planner generates MVP spec
-> manager chooses one implementation slice
-> coder worker executes
-> verifier runs deterministic checks
-> reviewer evaluates evidence
-> manager decides done / retry / ask human
-> final summary
```

## 2. 技术栈建议

### 主语言

推荐：Python

原因：

- LangGraph Python 生态成熟。
- OpenHands SDK 是 Python-first。
- shell、git、subprocess、文件处理都简单。
- 后续可接入 Aider / Cursor SDK / Claude Code CLI。

### 主控制层

```text
LangGraph
```

负责：

- state machine
- node routing
- loop control
- human checkpoint
- persistence/checkpoint

### 执行 worker

v0.1 先不要深接 OpenHands。

第一版建议：

```text
Coder Worker = local command adapter
```

也就是先支持以下几种执行方式之一：

- `aider` CLI
- `cursor-agent` / Cursor SDK 后续接入
- 手动 stub coder，用于先跑通 graph

优先级：

```text
1. stub coder
2. local shell/aider adapter
3. Cursor SDK adapter
4. OpenHands adapter
```

### 验证层

```text
shell commands + git diff
```

负责：

- `git diff`
- `git status`
- `npm test` / `pytest` / custom test command
- `lint`
- `typecheck`
- build/smoke test

## 3. v0.1 不做什么

暂不做：

- UI
- Web app
- daemon
- plugin system
- cloud execution
- automatic PR
- automatic commit
- full OpenHands integration
- `ruflo` evaluation
- complex long-term memory
- multi-user/team permissions
- generic agent marketplace

## 4. 推荐目录结构

```text
ai-cockpit/
  pyproject.toml
  README.md
  .ai-cockpit/
    memory/
      user.md
      project.md
      preferences.md
    workflows/
      idea-to-mvp.yaml
      fix-bug.yaml
    history/
  src/
    ai_cockpit/
      __init__.py
      cli.py
      config.py
      state.py
      graph.py
      prompts/
        planner.md
        reviewer.md
        manager.md
      nodes/
        intake.py
        planner.py
        coder.py
        verifier.py
        reviewer.py
        decision.py
        summary.py
      workers/
        base.py
        stub_worker.py
        shell_worker.py
        aider_worker.py
      tools/
        git.py
        shell.py
        files.py
      memory/
        loader.py
        recorder.py
      models/
        task_spec.py
        review_result.py
        verification_result.py
  tests/
    test_graph_smoke.py
    test_verifier.py
```

## 5. 核心数据结构

### TaskState

```python
class TaskState(TypedDict, total=False):
    user_input: str
    mode: Literal["exploration", "task"]
    project_root: str
    memory_context: str

    idea: str
    mvp_spec: str
    acceptance_criteria: list[str]
    implementation_slice: str

    coder_result: str
    git_diff: str
    git_status: str
    verification_result: VerificationResult
    review_result: ReviewResult

    decision: Literal["done", "retry", "ask_human", "stop"]
    loop_count: int
    max_loops: int
    final_summary: str
```

### VerificationResult

```python
class VerificationResult(TypedDict):
    passed: bool
    commands: list[dict]
    git_diff: str
    git_status: str
```

### ReviewResult

```python
class ReviewResult(TypedDict):
    passed: bool
    issues: list[str]
    risk_level: Literal["low", "medium", "high"]
    suggested_fix: str
```

## 6. LangGraph 节点设计

### 6.1 intake node

输入：

- 用户原始输入
- 当前目录
- memory 文件

输出：

- `mode`
- `memory_context`
- 初始 `loop_count`

第一版可以默认全部走 `exploration`。

### 6.2 planner node

职责：

- 把 idea 收敛为 MVP spec
- 生成 acceptance criteria
- 选择一个最小 implementation slice

输出：

- `mvp_spec`
- `acceptance_criteria`
- `implementation_slice`

### 6.3 coder node

职责：

- 把 `implementation_slice` 交给 worker 执行
- v0.1 可先使用 stub worker，不一定真实改代码
- 后续接 Aider / Cursor SDK / OpenHands

输出：

- `coder_result`

### 6.4 verifier node

职责：

- 读取 `git diff`
- 读取 `git status`
- 跑配置里的 test/lint/typecheck 命令
- 保存原始输出

输出：

- `verification_result`
- `git_diff`
- `git_status`

### 6.5 reviewer node

职责：

- 不信任 coder 的自我总结
- 只基于 `mvp_spec + acceptance_criteria + git_diff + verification_result`
- 判断是否通过

输出：

- `review_result`

### 6.6 decision node

职责：

- 如果 reviewer pass，进入 summary
- 如果 fail 且 `loop_count < max_loops`，回到 coder 或 planner
- 如果 fail 且达到 max loop，进入 ask_human
- 如果涉及产品判断，进入 ask_human

输出：

- `decision`

### 6.7 summary node

职责：

- 输出最终总结
- 包含完成情况、证据、未解决问题、建议下一步

## 7. Graph 结构

```text
START
-> intake
-> planner
-> coder
-> verifier
-> reviewer
-> decision
   -> done: summary -> END
   -> retry: coder
   -> ask_human: summary -> END
   -> stop: summary -> END
```

v0.1 只允许最多 1 次 retry。

## 8. CLI 设计

命令：

```bash
ai-cockpit "我想做一个自动整理 PR review 的工具"
```

可选参数：

```bash
ai-cockpit "..." --root .
ai-cockpit "..." --max-loops 1
ai-cockpit "..." --mode exploration
ai-cockpit "..." --dry-run
ai-cockpit "..." --test-command "npm test"
```

第一版行为：

- 默认读取当前目录
- 默认 dry-run 可先不开真实 coder
- 输出 graph 每一步摘要
- 最后输出 final summary

## 9. Memory 设计

v0.1 只做文件加载，不做自动更新。

读取：

```text
.ai-cockpit/memory/user.md
.ai-cockpit/memory/project.md
.ai-cockpit/memory/preferences.md
```

如果文件不存在，跳过。

示例 `preferences.md`：

```text
- 偏好小 diff
- 不做无关重构
- 修改后必须跑测试
- 不自动 commit
- 不确定产品取舍时先问人
```

## 10. Prompt 策略

### Planner Prompt

目标：

- 不直接写大方案
- 先收敛 MVP
- 输出清晰 acceptance criteria
- 只选择一个最小 implementation slice

### Reviewer Prompt

硬规则：

- 默认怀疑
- 不根据 coder summary 判断
- 只根据 evidence 判断
- 如果测试失败，默认 fail
- 如果 diff 超出任务范围，fail
- 如果 acceptance criteria 没覆盖，fail

### Manager Prompt

职责：

- 控制 loop
- 不无限 retry
- 产品判断交给人
- 输出下一步建议

## 11. 第一条可运行 Demo

不要求第一版真的修改复杂代码。

Demo 目标：

```bash
ai-cockpit "我想做一个工具，帮我把模糊 idea 收敛成 MVP spec"
```

期望输出：

```text
1. MVP spec
2. acceptance criteria
3. implementation slice
4. verifier result
5. reviewer result
6. final decision
```

如果没有真实代码修改，`coder node` 可以先返回：

```text
Stub worker: no code changes were made.
```

这样可以先验证 LangGraph 流程、状态传递、review/decision 逻辑。

## 12. 第二条 Demo

目标：接入一个轻量 worker。

可选：

```text
Aider CLI
Cursor SDK
```

流程：

```text
planner 生成 implementation_slice
-> coder worker 接收受控任务包
-> worker 修改代码
-> verifier 读取 diff + 跑测试
-> reviewer 判断
```

## 13. 验收标准

v0.1 完成标准：

- CLI 可以运行
- LangGraph 流程可以完整走完
- TaskState 在节点之间正确传递
- Planner 能输出 MVP spec 和 acceptance criteria
- Verifier 能读取 git diff/status
- Verifier 能运行至少一个 shell command
- Reviewer 能基于 evidence 输出 pass/fail
- Decision 能控制 done/retry/ask_human
- 最大 loop 有限制
- 最终 summary 清楚说明结果和证据

## 14. 最小安全规则

默认禁止：

- 自动 commit
- 自动 push
- 自动发 PR
- 自动发邮件
- 删除文件
- 大范围重构
- 修改 secrets

默认要求：

- 所有代码修改必须有 diff
- 所有验证必须保留原始输出
- reviewer 不能只看 coder summary
- loop 最多 1 次
- 不确定就 ask_human

## 15. 开发顺序

推荐按这个顺序让 automation 实现：

```text
Step 1: 创建 Python 项目骨架
Step 2: 定义 TaskState / result types
Step 3: 实现 memory loader
Step 4: 实现 shell/git tools
Step 5: 实现 verifier node
Step 6: 实现 planner/reviewer stub
Step 7: 实现 LangGraph graph
Step 8: 实现 CLI
Step 9: 跑 smoke test
Step 10: 接入第一个真实 coder worker
```

不要让 automation 一次性实现所有 worker。

## 16. v0.2 再做

v0.2 可以考虑：

- OpenHands worker
- Cursor SDK worker
- Aider worker
- SQLite/Postgres checkpoint
- memory update suggestion
- workflow templates
- human interrupt/resume
- browser verifier
- PR review workflow

## 17. 当前推荐下一步

下一步不是继续写大文档，而是创建项目骨架并实现 smoke test。

最小任务：

```text
Create a Python CLI project named ai-cockpit.
Implement a LangGraph flow with intake -> planner -> coder_stub -> verifier -> reviewer -> decision -> summary.
The first version can use stub LLM outputs and no real code edits.
It must run from CLI and print final TaskState summary.
```

这一步完成后，再接真实 worker。

