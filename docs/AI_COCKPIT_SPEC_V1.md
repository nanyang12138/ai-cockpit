# Personal AI Cockpit / Agentic Workflow OS

讨论收敛文档 v1.0

## 1. 核心结论

这个项目不应该被定义为一个新的通用 multi-agent framework、一个新的 IDE、一个新的 Dify / LangGraph / CrewAI，或者一个简单的 API wrapper。

更准确的定义是：

> 一个围绕个人工作流的 AI 管理层，用来调度现有 AI 工具、保留长期上下文、执行任务循环、验证结果，并在必要时让人类接管。

它的价值不在于重新实现模型能力，而在于把现有 AI 工具变成一个可控、可验证、可持续优化的工作系统。

本次讨论后的关键修正：

> 如果你的时间只有约 30% 是重复工作，剩下约 70% 都是在开发新 idea，那么系统的主模式不应该是简单任务自动化，而应该是 idea 落地导向的 multi-agent exploration loop。

因此，这个项目的核心不是：

```text
Task automation first
```

而是：

```text
Idea execution first
Task automation second
```

重复任务仍然重要，但它更像是 exploration 成功后沉淀出来的稳定流程，而不是系统的主轴。

## 2. 需要警惕的重复造轮子

如果项目目标是下面这些，重复造轮子的风险很高：

- 通用 agent 编排框架
- 通用 planner / coder / reviewer 系统
- 通用 workflow engine
- 通用模型路由平台
- 通用 no-code AI automation 平台
- 更好的 Cursor / Claude Code / OpenHands

这些方向已经有大量工具在做，例如：

- LangGraph
- AutoGen
- CrewAI
- LlamaIndex Workflows
- Dify
- Flowise
- n8n
- Aider
- OpenHands
- SWE-agent
- Cursor
- Claude Code

因此，项目不应该从零做一个大平台。

正确策略是：

> 现有工具负责能力，你的小系统负责流程、记忆、约束、验证和人类接管。

## 3. 项目真正值得做的部分

通用工具解决的是：

- 如何调用模型
- 如何编排 agent
- 如何连接工具
- 如何执行 workflow

但它们通常不解决你的个人工作问题：

- 你这个 repo 的规则是什么
- 你喜欢什么代码风格
- 你每次 PR review 怎么处理
- 你常做哪些任务
- 什么时候可以自动执行
- 什么时候必须问你
- 失败几次必须停下来
- 你更信任 Cursor、Claude Code 还是 shell
- 你的长期项目上下文是什么

所以真正值得做的不是通用平台，而是一层有明确立场的个人 multi-agent 执行层：

```text
User intent
-> Personal AI Cockpit
-> Memory + Workflow + Policy
-> Opinionated Agent Team
-> Cursor / Claude Code / shell / browser / other tools
-> Verifier
-> Reviewer
-> Human checkpoint
```

这里的重点不是做一个任何人都能配置任意 agent graph 的框架，而是做一个专门服务于你个人 idea 落地方式的 agent team。

## 4. 两类任务模式

系统必须同时支持两类工作。

但两类模式的优先级不是完全对等的。基于当前判断：

```text
Exploration Mode = 主模式
Task Mode = 从成功探索中沉淀出的缓存模式
```

也就是说，系统首先要擅长把模糊 idea 推进成可验证产物；当某些路径被反复验证有效后，再把它们固化为 Task Mode workflow。

### 4.1 Task Mode: 规律性任务

这类任务有稳定流程，可以沉淀成模板。

Task Mode 的定位不是系统核心创新，而是效率缓存。它服务于你那约 30% 的重复工作，也服务于 Exploration Mode 跑多之后形成的稳定套路。

示例：

- 修一个小 bug
- 回复 PR review
- 跑测试并总结失败原因
- 写邮件
- 生成日报
- 总结会议 action items

特点：

- 流程明确
- 可以模板化
- 重复频率高
- 成功标准相对清楚

这类任务应该被沉淀为 workflow。

例如：

```text
fix-bug workflow
1. 读取用户输入和当前 repo 状态
2. 找相关文件和错误线索
3. 生成修复计划
4. 调用 coding agent 修改
5. 跑 lint / test / typecheck
6. review diff
7. 不通过则带反馈再循环一次
8. 输出总结
```

### 4.2 Exploration Mode: 非规律性 idea 落地

这类任务没有固定流程，是项目的核心价值点，也是系统的主模式。

示例：

- 我有一个新产品 idea，想落地成 MVP
- 我想做一个新功能，但还不确定方案
- 我遇到一个复杂问题，需要边探索边实现
- 我想把一个模糊需求变成可运行原型

特点：

- 初始目标模糊
- 需要多轮澄清
- 需要产品判断
- 需要方案取舍
- 需要持续验证
- 需要人类 checkpoint

典型流程：

```text
idea
-> clarify
-> spec
-> plan
-> build
-> verify
-> review
-> refine
-> human checkpoint
```

这里确实需要 agentic flow，甚至需要 multi-agent。但 multi-agent 的目的不是让 AI 互相聊天，而是把模糊目标转化为可验证的工程过程。

对你的场景来说，Exploration Mode 不应该是附加能力，而应该是默认能力。它负责回答：

- 这个 idea 是否值得继续做
- MVP 范围应该多小
- 先验证什么
- 技术路径怎么选
- 当前实现是否偏离原始目标
- 是否过度设计
- 下一步应该继续、砍掉、转向，还是问你

所以 Exploration Mode 的核心不是 Coder Agent，而是 Manager Agent。Coder 负责执行，Manager 负责方向、节奏、边界和停止条件。

## 5. IDE 的角色

Cursor / IDE 不应该被替代，而应该被系统使用。

IDE 的角色有三层：

### 5.1 执行环境

通过 Cursor Agent、Claude Code 或其他 coding agent，在当前 repo 中读文件、改代码、运行命令。

### 5.2 人工接管界面

当系统不确定、冲突太多、需求需要你判断、或者自动循环失败时，回到 IDE 让你接管。

### 5.3 调试界面

你可以在 IDE 中查看：

- diff
- terminal output
- lint result
- test result
- agent 输出
- 当前文件状态

所以关系不是：

```text
Personal AI Cockpit replaces Cursor
```

而是：

```text
Personal AI Cockpit orchestrates Cursor / Claude Code / shell
Cursor remains execution and human fallback interface
```

## 6. 不需要每次重复输入上下文

系统应该把重复信息沉淀成 memory 和 workflow。

例如目录结构：

```text
.ai-cockpit/
  memory/
    user.md
    project.md
    preferences.md
  workflows/
    fix-bug.yaml
    pr-review.yaml
    idea-to-mvp.yaml
  history/
    task-2026-05-15.json
```

可以记录：

- 我喜欢小 diff
- 不要无关重构
- 修改前先理解上下文
- 修完必须跑测试
- review 要严格
- 遇到产品取舍先问我
- 这个 repo 的启动命令
- 这个 repo 的测试命令
- 这个项目的架构约束

最终体验应该是：

```bash
ai "修这个 bug"
```

系统自动补全：

```text
用户偏好
项目背景
代码风格
禁止事项
测试命令
review 标准
历史类似任务经验
```

## 7. 系统是否可以自我优化

可以，但必须有限制。

适合自动总结的内容：

- 用户偏好
- 常见任务类型
- 项目启动方式
- 测试命令
- 成功 workflow
- 失败原因
- reviewer 常见检查项

不适合无确认自动修改的内容：

- 核心系统策略
- 安全规则
- 权限边界
- 是否允许自动提交
- 是否允许改大范围代码
- 是否允许自动发邮件、发 PR、发消息

推荐机制：

```text
系统发现规律
-> 生成 memory / workflow 更新建议
-> 用户确认
-> 下次生效
```

例如：

```text
我注意到你连续 3 次要求：
- 不要大重构
- 修复后必须跑测试
- reviewer 要检查 diff 是否越界

是否保存为默认代码任务规则？
```

## 8. Multi-agent 的真实价值

multi-agent 有价值，但不是因为 agent 数量多，而是因为不同角色有不同责任、权限和输入证据。

在这个项目里，multi-agent 不是边缘功能，而是 Exploration Mode 的主能力。原因是 idea 落地不是单步执行，而是持续做判断：

```text
idea 是否成立
-> MVP 如何收敛
-> 技术方案如何选择
-> 当前实现是否接近目标
-> 是否继续投入
-> 是否需要人类判断
```

这些判断不是普通 IDE coding agent 的强项。IDE agent 更适合作为 worker，真正的核心应该是 Manager Agent 管理整个探索过程。

但这里仍然不应该做通用 multi-agent 平台。更准确的定位是：

> 一个 opinionated agent team，专门服务 idea -> MVP -> implementation -> review -> iteration。

推荐角色：

```text
Manager Agent
  控制流程、拆任务、决定继续/停止/问人

Planner Agent
  将模糊目标变成方案、任务、验收标准

Coder Agent
  调用 Cursor / Claude Code / Codex 执行代码修改

Verifier
  执行确定性检查，如 test / lint / typecheck / build / smoke test

Reviewer Agent
  基于任务规格、diff 和验证结果挑问题

Writer Agent
  生成总结、PR 回复、邮件、状态报告
```

其中最重要的是 Manager、Verifier 和 Reviewer。

## 9. 防止 AI 欺骗 AI

这是系统最大风险之一。

风险不是 AI 真有恶意，而是：

- Coder agent 过度自信
- Reviewer agent 被 coder 的解释带偏
- 多个 agent 共享同样盲区
- 没有真实验证时产生假完成感
- agent 为了完成任务而降低标准

因此系统不能设计成：

```text
Coder says done
-> Reviewer reads coder summary
-> Reviewer says pass
```

正确方式是：

```text
Coder produces changes
-> System collects evidence
-> Verifier runs deterministic checks
-> Reviewer reviews evidence, not coder self-report
-> Manager decides pass / retry / ask human
```

Reviewer 必须基于事实：

- git diff
- test output
- lint output
- typecheck output
- build result
- browser result
- logs
- screenshots
- acceptance criteria
- task spec

硬规则：

- Coder 不能决定自己是否完成
- Reviewer 不能只看 Coder 总结
- 能用程序验证的，不交给 AI 判断
- 每个任务必须有 acceptance criteria
- Reviewer 默认怀疑，而不是默认通过
- 循环次数有限
- 关键产品判断交给人

### 9.1 多步 plan 是调度产物，不是 reviewer 证据（B.6 addendum, 2026-05-16）

B.6 引入了 `docs/plans/<plan_id>.plan.yaml` 多步 plan 工件以及
`ai-cockpit plans run <plan_id> <slice_id>` 执行入口。该工件**只是
调度层 metadata**：它告诉系统下一步要跑哪个 slice，以及 slice 之间
的依赖应通过 git log 中的 `[<plan_id>/<slice_id>]` marker 验证。
它**不是** reviewer 的正向证据来源。

因此在 §9 evidence-only reviewer 这条硬规则之下，B.6 必须同时满足：

- plan YAML 的 `idea` / `why` / `scope_must` / `acceptance_criteria`
  等任何字段**不得**字节级地出现在 reviewer prompt（已由 anti-
  deception 回归测试 #5 在 `tests/test_llm_planner_reviewer.py`
  中钉死）。
- `plans run` 在把 slice 的 `title / why / scope_must / scope_out
  / dod / test_commands` 注入 `TaskState` 时，它们走的是和"人输入
  一个 idea"完全相同的通道；plan 的整体 `idea` 字段仅作为背景
  context 附带，不进入 acceptance criteria。
- 依赖检查的真值来源**只**是 `git log` 中的 marker；任何 in-process
  缓存、plan 文件自身的"已完成"标记、或 reviewer 的自报，都不构成
  授权。
- `plans list` / `plans show` 是纯只读视图，仅汇总 `docs/plans/*`
  以及 `git log` 中的 marker；它们不修改任何源、不写 memory、不
  调 LLM、也不进入 reviewer prompt。

## 10. 最小可行架构

v0.1 不应该做完整 OS。

但 v0.1 也不应该退化成简单任务 wrapper。由于主场景是 idea 开发，v0.1 的默认主流程应该是一个很窄但完整的 Exploration Loop：

```text
idea intake
-> clarify
-> MVP spec
-> technical plan
-> implementation slice
-> build
-> verify
-> review
-> decision
```

Task Mode 可以同时支持，但它应当作为较稳定的 workflow，而不是压过 Exploration Mode 的主线。

v0.1 应该只做：

- CLI entry
- memory loader
- task spec generator
- exploration manager
- planner / architect role
- Cursor / Claude Code adapter
- verifier
- reviewer
- max 1-2 次 loop
- final summary

推荐 Task Mode 执行流：

```text
user input
-> load memory
-> classify task
-> generate task spec
-> run coder agent
-> collect diff
-> run tests / lint / typecheck
-> run reviewer
-> if pass: summarize
-> if fail: retry with feedback
-> if still fail: ask human
```

推荐 Exploration Mode 执行流：

```text
idea input
-> load memory
-> ask clarifying questions if needed
-> generate MVP spec
-> generate acceptance criteria
-> choose implementation slice
-> run coder agent
-> collect evidence
-> run verifier
-> run reviewer
-> manager decides continue / refine / pivot / stop / ask human
```

伪代码：

```ts
for (let i = 0; i < maxLoops; i++) {
  const coderResult = await runCoder(taskSpec);

  const diff = await getGitDiff();
  const verification = await runVerification(taskSpec.testCommands);

  const review = await runReviewer({
    taskSpec,
    diff,
    verification,
  });

  if (review.pass) {
    return summarize(coderResult, review);
  }

  taskSpec = applyFeedback(taskSpec, review.feedback);
}

return askHuman("Max loop reached");
```

## 11. Cursor Agent / Claude Code 不是魔法 API

调用 Cursor Agent 或 Claude Code 只是执行通道。

如果只发：

```text
帮我修这个 bug
```

那就是普通 prompt tool。

你的系统应该发受控任务包：

```text
目标
上下文
约束
禁止事项
允许修改范围
成功标准
必须运行的检查
失败时输出什么
```

例如 TaskSpec：

```ts
type TaskSpec = {
  objective: string;
  context: string;
  constraints: string[];
  successCriteria: string[];
  allowedFiles?: string[];
  forbiddenActions: string[];
  testCommands: string[];
};
```

这才是让 agent 按你的要求执行的关键。

## 12. v0.1 项目边界

### 应该做

- 本地 CLI
- 当前 repo 内执行
- idea-to-plan
- idea-to-MVP-spec
- plan-to-code
- exploration loop
- manager decision step
- diff review
- test / lint verifier
- memory 文件
- workflow 模板

### 不应该做

- UI
- 插件系统
- 通用 agent marketplace
- 多模型复杂路由
- 长期后台守护进程
- 团队权限系统
- 云端任务平台
- 复杂可视化 workflow builder

## 13. 推荐目录结构

```text
src/
  cli.ts
  manager.ts
  types.ts
  memory/
    load-memory.ts
    update-suggestions.ts
  workflows/
    classify-task.ts
    load-workflow.ts
  agents/
    cursor-agent.ts
    claude-code.ts
    planner.ts
    reviewer.ts
    writer.ts
  tools/
    git.ts
    shell.ts
    verifier.ts

.ai-cockpit/
  memory/
    user.md
    project.md
    preferences.md
  workflows/
    fix-bug.yaml
    idea-to-mvp.yaml
  history/
```

## 14. Open Source Landscape & Build-vs-Buy

当前判断需要进一步收紧：

> multi-agent 基础设施基本不应该自研，应该优先复用成熟开源项目。

这个项目要避免把时间花在已经被别人做得很好的部分上。真正要做的是在现有工具之上，构建你的个人 idea execution layer。

### 14.1 候选开源项目分类

#### Agent 编排 / Workflow 底座

- `LangGraph`
- `CrewAI`
- `AutoGen`
- `Agno`
- `PydanticAI`
- `smolagents`

这类项目主要解决：

- agent runtime
- workflow graph
- multi-agent coordination
- state management
- tool calling
- checkpoint
- human-in-the-loop

其中 `LangGraph` 更适合显式状态机、条件分支、循环和人工中断；`CrewAI` 更适合角色式团队原型；`AutoGen` 更适合对话式 multi-agent；`Agno`、`PydanticAI`、`smolagents` 更偏轻量 agent app 或生产 SDK。

#### Claude Code-native Orchestration

- `ruflo`

`ruflo` 值得重点评估，因为它的定位非常接近当前想法：

```text
Claude Code
+ multi-agent swarm
+ workflows
+ memory
+ hooks
+ MCP
+ autopilot
+ RAG
+ Claude Code / Codex integration
```

它可能已经覆盖了你原本想自研的大量能力：

- swarm coordination
- agent registry
- Claude Code hooks
- workflow templates
- memory / RAG
- autopilot loop
- code quality plugins
- browser / test / diff risk 相关插件

但需要验证：

- 实际稳定性如何
- alpha 版本是否适合长期依赖
- 是否过度绑定 Claude Code
- 是否容易接入 Cursor SDK / OpenHands / SWE-agent
- 完整安装对项目目录的侵入性是否可接受
- “self-learning / 100+ agents / swarm intelligence”是否真的有工程价值，还是主要是包装

#### Coding Agent / 执行层

- `OpenHands`
- `SWE-agent`
- `Aider`
- `Cursor SDK`
- `Claude Code`
- `Codex`

这类项目主要解决：

- 读代码
- 改代码
- 执行 shell
- 修 issue
- 跑测试
- 生成 PR
- 自动处理一部分软件工程任务

它们更适合作为 worker，而不是你的系统 manager。

#### Issue-to-PR / Autonomous Dev Workflow

- `Looper`
- `autonomous-dev-team`
- `Auto Code`
- `AI-SDLC Framework`
- `three-body-agent`

这类项目已经很接近：

```text
issue
-> planner
-> worker
-> reviewer
-> fixer
-> CI
-> PR
```

它们必须重点研究，因为它们可能已经覆盖了你想做的“AI 管理 AI、AI 执行、AI 审查”的工程闭环。

### 14.2 不应该自研的部分

以下部分默认不自研，除非评估后确认现有工具无法满足：

- agent runtime
- multi-agent messaging
- graph engine
- workflow engine
- checkpoint system
- tool calling protocol
- coding sandbox
- autonomous PR pipeline
- generic memory framework
- generic plugin system
- generic swarm coordination

这些都是成熟开源项目正在解决的问题。

### 14.3 应该自己做的部分

你应该自己做的是更靠近个人工作方式的一层：

- idea intake 方式
- MVP 收敛规则
- 你的产品判断标准
- 你的技术取舍偏好
- 你的 reviewer 严格程度
- 你的 human checkpoint 规则
- 你的项目上下文和长期 memory
- 你的 TaskSpec 格式
- 你的 acceptance criteria 模板
- 不同底座之间的适配和选择策略

也就是说：

```text
Open source = capabilities
Your system = opinionated personal operating layer
```

### 14.4 初步候选优先级

第一优先级：

- `LangGraph`：因为它适合做可控、显式、可审计的 exploration state machine。
- `OpenHands`：因为它适合作为较完整的 coding worker。
- `Aider`：因为它轻量、Git-friendly，适合本地快速改代码。
- `Cursor SDK`：因为它最贴近当前 IDE 工作环境，适合作为人工接管和本地 worker 桥接。

第二优先级：

- `SWE-agent`：适合 issue / bug 修复类任务。
- `Agno` / `smolagents`：适合轻量 agent app 或快速原型。
- `CrewAI` / `AutoGen`：适合参考角色式或对话式 multi-agent 模式。

暂不采用：

- `ruflo`：虽然方向贴近，但当前目标优先安全、稳定、可控，不做 swarm 平台试验。

必须单独研究：

- `Looper`
- `AI-SDLC Framework`
- `autonomous-dev-team`
- `Auto Code`

因为它们可能已经覆盖了 autonomous dev workflow 的完整闭环。

### 14.5 Build-vs-Buy 决策原则

每个模块都按下面的问题判断：

```text
这是通用 agent 能力吗？
-> 是：优先复用开源项目

这是我的个人工作方式吗？
-> 是：可以自己实现

这是为了 idea 落地的判断标准吗？
-> 是：应该自己实现

这是工具执行能力吗？
-> 是：优先接入现有 worker
```

最终目标不是做一个新的开源 agent 框架，而是选择一个或多个优秀底座，组合成个人化的 idea execution system。

### 14.6 底座详细评估

本节按“安全、稳定、可控、贴合 idea-to-MVP 主流程”的优先级评估。

#### 结论先行

如果目标是“最好、最安全、最稳定”，当前推荐不是单押某个一体化 swarm 平台，而是采用分层架构：

```text
主控制层：LangGraph
执行层：OpenHands / Cursor SDK / Aider
特定任务：SWE-agent / mini-SWE-agent
暂不采用：ruflo
```

原因：

- 你的核心风险不只是“agent 能不能干活”，而是“过程是否可控、可恢复、可审计、可人工中断”。
- 一体化 swarm 系统看起来能力强，但如果内部决策不可控、安装侵入性高、版本变化快，反而不适合作为最安全的第一底座。
- idea 落地需要明确状态机、checkpoint、human checkpoint、verification gate，这更接近 LangGraph 的强项。

#### LangGraph

定位：

```text
显式状态机 / workflow graph / checkpoint / human-in-the-loop 底座
```

优点：

- 状态流显式，适合建模 `idea -> spec -> plan -> build -> verify -> review -> decision`。
- 支持 checkpoint，每一步状态可持久化。
- 支持 human-in-the-loop interrupt，适合在产品判断、权限动作、失败循环时暂停问人。
- 支持恢复、调试、历史状态查看，适合长期 exploration loop。
- 不强绑定某个 coding agent，可以接 Cursor、Claude Code、OpenHands、Aider、shell。
- 相比 swarm 黑盒，更容易审计和限制行为。

风险：

- 需要你自己定义状态、节点和边，第一版开发成本比 CrewAI/ruflo 高。
- 如果设计不好，容易把 graph 做复杂。
- 它解决的是 orchestration，不直接解决“写代码能力”。

适配你的项目：

```text
非常适合作为 Manager / Controller 层。
```

建议：

```text
作为最稳的主底座。
```

#### ruflo

定位：

```text
Claude Code-native multi-agent orchestration / swarm / workflow / memory 平台
```

优点：

- 与 Claude Code 结合紧密，和你的“让 AI 管理 AI、AI 执行、AI 审查”想法很接近。
- 提供 swarm、autopilot、workflow、memory、RAG、MCP、hooks 等能力。
- README 中说明完整 CLI 安装包含大量 agents、commands、skills、MCP server、hooks、daemon。
- 有 code quality、testgen、browser、diff risk 等插件方向，覆盖你的 verifier/reviewer 需求。
- 可能极大减少你自研 multi-agent 基础设施的工作量。

风险：

- 表面能力非常多，实际稳定性必须通过真实任务验证。
- 版本看起来仍偏 alpha / 快速演进，不适合作为最安全稳定的第一选择。
- 完整安装会写入 `.claude/`、`.claude-flow/`、`CLAUDE.md`、hooks、settings，侵入性较高。
- 绑定 Claude Code 较深，未来接 Cursor SDK、OpenHands、Aider 时可能受限。
- “100+ agents / self-learning / swarm intelligence”这类能力需要验证是否真的提升工程质量，而不是增加不可控复杂度。

适配你的项目：

```text
高度相关，但当前不采用。
```

建议：

```text
暂不验证，暂不集成，避免把第一版复杂度带偏到 swarm 平台评估。
```

如果未来重新评估，再使用以下试验标准：

- 是否能从 idea 生成可执行 plan。
- 是否能约束 agent 不越界改代码。
- 是否能跑 test / lint / review。
- 是否能清晰解释每个 agent 做了什么。
- 是否能暂停并让人类决策。
- 卸载后是否不污染项目。

#### OpenHands

定位：

```text
autonomous coding worker / software agent SDK / Docker sandbox
```

优点：

- 适合作为代码执行 worker。
- 提供 Bash、file editing、browser、MCP 等工具能力。
- 支持 DockerWorkspace，能把 agent 执行放在容器中，隔离性更好。
- 有 SDK / REST server 形态，适合作为你的 controller 调用的 worker。
- 比直接让本机 agent 任意操作更安全。

风险：

- 它更像执行层，不是你的 idea manager。
- Docker / server 部署增加初始复杂度。
- 对日常轻量任务可能偏重。

适配你的项目：

```text
很适合作为安全执行层，尤其适合需要 sandbox 的 build / verify / code change。
```

建议：

```text
作为 LangGraph 的默认 coding worker 候选。
```

#### Aider

定位：

```text
轻量本地 AI pair programmer / git-centric coding worker
```

优点：

- 简单、成熟、Git-friendly。
- repo map 能帮助理解代码结构。
- 支持 lint/test 命令，适合本地快速迭代。
- 侵入性较低，适合 v0.1 快速验证。

风险：

- 不是完整 autonomous workflow 平台。
- 不适合做 Manager。
- sandbox 能力不如 OpenHands。

适配你的项目：

```text
适合作为轻量 worker，尤其适合小 diff、本地快速修改。
```

建议：

```text
如果你想最快跑通 v0.1，可以先接 Aider 或 Cursor SDK；如果更重视隔离安全，用 OpenHands。
```

#### Cursor SDK

定位：

```text
Cursor agent execution interface
```

优点：

- 能直接利用 Cursor IDE / agent 能力。
- 对你当前工作环境最自然。
- 适合作为本地 worker 或 human fallback 的桥。

风险：

- 不是开源底座。
- 不是 multi-agent workflow engine。
- 需要你自己做 controller、verification、policy。

适配你的项目：

```text
适合作为 IDE-native worker，不适合作为主 orchestration 底座。
```

建议：

```text
和 LangGraph 搭配：LangGraph 管理流程，Cursor SDK 执行具体代码任务。
```

#### SWE-agent / mini-SWE-agent

定位：

```text
issue-to-fix / SWE-bench 风格 coding agent
```

优点：

- 在修 issue / bug 这类任务上很强。
- Docker sandbox / benchmark 方向成熟。
- mini-SWE-agent 更简单，适合研究和定制。

风险：

- SWE-agent 主项目已有 maintenance-only 信号，后续重点转向 mini-SWE-agent。
- 更适合明确 issue，不适合从模糊 idea 做产品收敛。
- 不适合作为你的主 manager。

适配你的项目：

```text
适合 Task Mode 或 bug-fix worker，不适合作为 Exploration Mode 主底座。
```

建议：

```text
作为特定任务 worker，而不是核心系统。
```

#### CrewAI / AutoGen

定位：

```text
角色式 / 对话式 multi-agent 框架
```

优点：

- 快速原型友好。
- 适合模拟团队角色和多 agent 对话。
- 学习成本相对低。

风险：

- 对你的核心诉求“可控、可审计、可暂停、可验证”的支持不如显式状态图自然。
- 容易变成 agent 互相聊天，产生看起来很忙但结果不可验证的问题。

适配你的项目：

```text
适合参考 agent role 设计，不建议作为最安全稳定的主底座。
```

#### Agno / PydanticAI / smolagents

定位：

```text
轻量 agent SDK / production LLM app framework
```

优点：

- 轻量、灵活。
- 适合快速构建 agent app。
- PydanticAI 的类型约束对结构化输出有帮助。
- smolagents 简单、可审计。

风险：

- 它们不是完整 idea-to-MVP workflow 产品。
- 你需要自己补很多 orchestration、checkpoint、decision loop。

适配你的项目：

```text
适合做组件或轻量原型，不是当前“最安全稳定主底座”的第一选择。
```

#### Looper / AI-SDLC Framework / autonomous-dev-team / Auto Code

定位：

```text
autonomous dev workflow / issue-to-PR pipeline
```

优点：

- 已经接近 `planner -> worker -> reviewer -> fixer -> CI -> PR` 的闭环。
- 非常值得研究，避免重复造轮子。

风险：

- 多数偏 GitHub issue / PR 自动化，不一定覆盖你的 idea intake 和 MVP 收敛。
- 可能更适合团队仓库自动化，而不是个人探索式产品开发。
- 需要逐个试跑验证成熟度。

适配你的项目：

```text
适合参考 Task Mode 和 PR 自动化，不一定适合作为 Exploration Mode 主底座。
```

### 14.7 推荐路线

#### 最安全稳定路线

```text
LangGraph
-> Manager / Planner / Decision / Human Checkpoint

OpenHands
-> sandboxed coding worker

Aider or Cursor SDK
-> lightweight local coding worker / IDE fallback

Your layer
-> idea intake / MVP criteria / memory / reviewer policy
```

这是当前最推荐路线。

理由：

- 控制层清晰，不被某个 swarm 平台绑死。
- LangGraph 负责状态、循环、checkpoint、human interrupt。
- OpenHands 负责安全隔离执行。
- Aider / Cursor SDK 保留轻量本地开发体验。
- 你的系统只写最有个人价值的部分。

#### 最快 MVP 路线

```text
LangGraph
-> minimal exploration loop

Cursor SDK or Aider
-> coding worker

local shell
-> verifier
```

这条路线最快验证你的核心假设：

```text
idea -> MVP spec -> code slice -> verify -> review -> decision
```

如果这个 loop 对你没有明显省时间，再强的底座都不值得继续。

### 14.8 当前推荐决策

当前最稳妥选择：

```text
主底座：LangGraph
执行 worker：OpenHands + Aider/Cursor SDK
特定 bug/issue worker：mini-SWE-agent
暂不采用：ruflo
```

明确不建议：

```text
第一阶段验证 ruflo 或直接以 ruflo 作为主底座
```

原因不是 `ruflo` 不好，而是它太一体化、太强绑定 Claude Code、安装侵入性较高、版本仍需验证。对于你最关心的“安全、稳定、可控”，第一版应该优先选择显式控制的架构，而不是把时间花在 swarm 平台试验上。

最终一句话：

> 用 LangGraph 做大脑和流程，用 OpenHands/Aider/Cursor 做手，暂时不采用 ruflo。

## 15. MVP 验证标准

不要用概念判断项目是否值得继续，用真实节省时间判断。

7 天内验证 3 个场景。其中最重要的是场景 3，因为它代表你的主使用场景。

### 场景 1: 修小 bug

目标：

- 能读取上下文
- 能修改代码
- 能跑测试
- 能 review diff
- 能给出可信总结

### 场景 2: 处理 PR review

目标：

- 能理解 review comment
- 能修改代码
- 能生成回复草稿
- 能避免无关改动

### 场景 3: idea 到 MVP plan

目标：

- 能追问关键问题
- 能收敛 MVP 范围
- 能生成工程计划
- 能实现一个小原型
- 能根据验证结果调整下一步
- 能在继续、缩小范围、转向、停止、问人之间做出明确建议

如果场景 3 不能明显省时间，不应该继续扩展架构。

如果场景 3 有价值，但场景 1 和场景 2 还不稳定，说明系统方向仍然成立，只是 Task Mode 的 workflow 沉淀还不够。

如果能省时间，再逐步扩展。

## 16. 最终定位

这个项目不是：

- 新的 AI 工具
- 新的 Skill 系统
- 新的 API wrapper
- 新的通用 agent framework
- 新的 IDE

它应该是：

> 一个以 idea 落地为核心，以个人上下文、multi-agent exploration loop、真实验证和人类 checkpoint 为基础的 AI 工作流管理层。

一句话：

> 让 AI 不只是执行单步任务，而是围绕你的 idea 持续澄清、规划、实现、验证、收敛，并在不确定时把控制权交回给你。

