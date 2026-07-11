# Hermes Agent 等方案适配调查报告

调查日期：2026-07-11

## 结论

Hermes Agent 可以把 Tutor Recommendation 包装成可对话、可定时、可通过 CLI 或消息平台触发的本地 Agent，但不应替代现有确定性的评分、身份、checkpoint 和质量审计逻辑。

推荐架构是：

```text
Hermes CLI / TUI / Telegram
           |
           v
受限的 tutor-recommendation MCP 服务
           |
           v
现有 Python CLI 与 ranking_policy
           |
           v
outputs / checkpoint / contact_status.json
           |
           v
现有 Viewer 表格与套磁日历
```

短期建议先做 Hermes 试点；长期如果需要生产级暂停恢复、人工审批节点和运行状态可视化，再考虑用 LangGraph 或 Microsoft Agent Framework 重构编排层。

## 当前项目适合 Agent 化的部分

适合交给 Agent 外壳的工作：

- 根据自然语言选择目标并调用现有三阶段命令。
- 按学校批量构建存在重叠关系的目标。
- 执行 checkpoint doctor、质量审计和人工抽查清单。
- 汇总推荐结果、归属待复核项和低置信身份。
- 生成套磁日历摘要和缺日期提醒。
- 定时检查缓存时效、旧 policy 工作簿和未完成 checkpoint。
- 从聊天入口打开某位教师的证据摘要或更新联系状态。

不适合交给自由 Agent 判断的部分：

- 修改画像权重、ranking policy 门槛或核心锚点规则。
- 根据研究方向猜测学院归属或教师身份。
- 自动把低置信 DBLP/arXiv/WebSearch 证据升级为强证据。
- 自动发送套磁邮件或批量改变联系状态。
- 绕过 checkpoint 完整覆盖或质量门禁。

这些边界应继续由当前代码、schema 和测试强制执行。

## Hermes Agent 评估

### 能力匹配

Hermes Agent 当前提供以下与本项目直接相关的能力：

- 原生 Windows、WSL2、Linux 和 macOS 支持。
- 可选择不同模型提供商或自建兼容端点。
- 支持本地 stdio 和远程 HTTP MCP 服务，并可限制单个 MCP 暴露的工具。
- 支持 agentskills.io 风格的技能、持久记忆和会话检索。
- 内置 cron，可指定项目工作目录并加载其中的 `AGENTS.md`。
- 支持 CLI、TUI、Telegram、Discord、Slack、WhatsApp 和 Signal 等入口。
- 支持本地、Docker、SSH、Modal、Daytona 和 Singularity 等执行后端。
- 对危险命令提供人工审批、智能审批、deny 规则和不可关闭的灾难命令阻断层。

截至调查日，官方仓库使用 MIT 许可证，最新公开 release 为 `v2026.7.7.2`，release 内容标注内部版本 `v0.18.2`。

### 优点

1. 最快获得自然语言入口

   不需要重写现有 Python 流程。只要把受控操作暴露为 MCP 工具，再写一个项目技能，就可以通过对话运行目标、查看审计结果和生成日历摘要。

2. 定时任务和消息投递现成

   可以安排每日 checkpoint 检查、每周质量审计或缓存过期报告，并把结果发送到指定聊天入口。

3. 与现有项目规则兼容

   cron 指定 `workdir` 后会加载项目 `AGENTS.md`。Hermes 技能也可以只描述如何调用现有 CLI，而不复制 ranking policy。

4. 模型和工具入口解耦

   MCP 层可以保持不变，Hermes 只充当一个可替换的客户端。未来换成其他 MCP host 时不需要重写业务工具。

### 风险与限制

1. Hermes 仍处于快速变化期

   当前 release 版本仍是 `0.x`，仓库更新非常频繁。配置、技能和网关行为需要锁定版本并通过升级测试后再更新。

2. 本地终端后端没有隔离

   `terminal.backend: local` 会直接在用户机器执行命令。项目包含私有画像和联系状态，正式运行更适合使用受限 MCP 工具；如果开放通用 shell，应使用 Docker/WSL2 隔离并限制挂载目录。

3. 自学习技能可能造成规则漂移

   Hermes 可以从经验创建或修改技能，但本项目的 evidence rules 不能由 Agent 自主改写。项目技能应设为人工维护，自动学习只能生成候选建议，不能覆盖正式规则。

4. Hermes memory 不是业务数据库

   官方 memory 有严格字符上限，适合存放偏好和短规则，不适合保存教师证据、目标进度或联系状态。权威数据仍应放在 workbook、checkpoint、manifest 和 `contact_status.json`。

5. 供应链和远程入口需要额外审计

   Windows 安装器会安装运行依赖和 Git Bash；可选 MCP 也可能执行安装脚本。正式环境应固定版本、审查 manifest，不启用不需要的消息平台和 MCP。

## 推荐的 MCP 工具边界

第一版 MCP 服务建议只暴露下面这些明确工具，不向 Hermes 暴露任意 Python 或 PowerShell 执行：

| 工具 | 权限 | 行为 |
|---|---|---|
| `list_targets` | 只读 | 返回目标键、学校、学院和输出状态 |
| `inspect_target` | 只读 | 返回 manifest、checkpoint 和当前工作簿概况 |
| `build_targets` | 写入 | 调用第一阶段；同校重叠目标必须联合构建 |
| `run_dblp_stage` | 写入/联网 | 调用 DBLP 阶段，不接受任意命令参数 |
| `run_completion_stage` | 写入/联网 | 调用完整研究阶段，默认禁止 partial finalize |
| `audit_targets` | 只读 | 调用 checkpoint doctor 和质量审计 |
| `list_affiliation_reviews` | 只读 | 返回学院归属待复核项 |
| `get_recommendations` | 只读 | 按目标和等级读取现有 policy 输出 |
| `calendar_summary` | 只读 | 返回日期、学校、学院分布和密集提醒 |
| `update_contact_status` | 写入 | 使用稳定教师 ID 更新一条联系状态 |

所有写工具都应：

- 使用结构化参数而不是自由命令字符串。
- 校验目标键来自 registry。
- 使用项目根目录下的固定路径。
- 返回运行 ID、manifest 和输出文件，而不是只返回自然语言。
- 对 destructive 或批量变更要求人工确认。
- 禁止读取或回传私有画像全文。

## Hermes 试点配置建议

- 使用单独的 Hermes home/profile，避免污染其他项目配置。
- 初期使用本机 CLI/TUI，不开启公网或消息平台入口。
- `approvals.mode` 使用 `manual`。
- `approvals.cron_mode` 使用 `deny`。
- 不使用 `--yolo`。
- 只启用自建的 Tutor Recommendation MCP。
- MCP 只访问当前仓库和 `outputs/`，不要暴露整个用户目录。
- API key 继续只放环境变量或 Hermes `.env`，不进入仓库和技能文件。
- 锁定 Hermes 版本；升级前跑本项目完整测试和 MCP 合约测试。
- cron 只运行只读审计；正式抓取仍由用户明确触发，直到稳定性验证完成。

## 其他方案比较

| 方案 | 最适合的角色 | 对当前项目的优势 | 主要代价 | 建议 |
|---|---|---|---|---|
| Hermes Agent | 个人 Agent 外壳、聊天入口、定时调度 | MCP、技能、cron、消息平台和 Windows 支持开箱即用 | 版本变化快；通用 Agent 权限面较大 | 最适合短期试点 |
| LangGraph | 确定性、可恢复的业务编排内核 | durable execution、checkpoint、人工中断和状态图适合三阶段流程 | 需要重写编排和状态模型 | 最适合长期核心编排 |
| Deep Agents | 带文件系统、技能和子 Agent 的开发框架 | 比 LangGraph 更快获得完整 Agent harness | 安全依赖工具/沙箱边界；仍需自行做调度和产品 UI | 可作为自研 Agent 的备选 |
| Microsoft Agent Framework | 企业级 Python/.NET Agent 与多 Agent 工作流 | checkpoint、human-in-loop、OpenTelemetry、声明式 Agent 和长期支持 | 框架较重，现项目暂无 Azure/.NET 必要性 | 企业部署时优先评估 |
| CrewAI | 角色型多 Agent 协作和事件 Flow | 高层抽象易于拆分“采集/核验/审计”角色 | 容易把确定性流水线过度 Agent 化 | 当前不优先 |
| OpenHands Agent Canvas | 编码 Agent 控制台与自动化 | 自托管 UI、计划任务、多种编码 Agent 后端 | 偏软件工程任务，不是领域业务运行时 | 适合开发运维，不适合替代 Viewer |

不建议新项目基于 AutoGen 起步。其官方仓库已进入 maintenance mode，并建议新用户迁移到 Microsoft Agent Framework。

## 推荐实施路线

### 阶段 0：保持现状

现有 Viewer、CLI、checkpoint 和 policy 保持权威，不先引入 Agent 依赖。

### 阶段 1：只读 Hermes 试点

实现一个最小 MCP 服务，只提供：

- `list_targets`
- `inspect_target`
- `audit_targets`
- `get_recommendations`
- `calendar_summary`

用 Hermes CLI/TUI 验证自然语言查询、Windows 路径、中文字段和私有数据边界。

### 阶段 2：受控写操作

加入三阶段运行和单条联系状态更新工具。每次写操作显示将执行的目标、阶段、输出目录和预计联网范围，并等待确认。

### 阶段 3：只读定时任务

启用每日/每周审计 cron，只发送报告，不自动重跑抓取，不修改联系状态。

### 阶段 4：决定长期编排层

如果需求仍以个人使用和消息触发为主，继续使用 Hermes 外壳即可。如果需要多人协作、任务队列、失败恢复、审批工作流和运行追踪，则把三阶段编排迁移到 LangGraph 或 Microsoft Agent Framework，Hermes 仍可作为其中一个 MCP 客户端。

## 最终建议

建议开展 Hermes 只读试点，但不把项目“整体迁移到 Hermes”。

最稳妥的组合是：

```text
业务真相与规则：现有 Python 模块、manifest、checkpoint、JSON
交互与调度：Hermes Agent
工具协议：项目专用 MCP
人工审阅：现有 Viewer 与套磁日历
未来生产编排：按需要评估 LangGraph / Microsoft Agent Framework
```

这样可以获得 Agent 入口的便利，同时保留当前项目最重要的可审计性、隐私边界和确定性质量门禁。

## 主要来源

- [Hermes Agent 官方仓库](https://github.com/NousResearch/hermes-agent)
- [Hermes Agent v2026.7.7.2 release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.7.2)
- [Hermes Security](https://hermes-agent.nousresearch.com/docs/user-guide/security)
- [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)
- [Hermes Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)
- [Hermes Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [Hermes Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- [LangGraph 官方仓库](https://github.com/langchain-ai/langgraph)
- [Deep Agents 官方仓库](https://github.com/langchain-ai/deepagents)
- [Microsoft Agent Framework 官方仓库](https://github.com/microsoft/agent-framework)
- [CrewAI 官方仓库](https://github.com/crewAIInc/crewAI)
- [OpenHands 官方仓库](https://github.com/OpenHands/OpenHands)
- [AutoGen 官方仓库](https://github.com/microsoft/autogen)
