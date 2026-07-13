# Tutor Recommendation

<p align="center">
  <img src="docs/assets/tutor-recommendation-icon.png" alt="Tutor Recommendation：本地导师推荐与套磁管理工作区" width="760">
</p>

Tutor Recommendation 是一个由 Coding Agent 驱动、本地运行、证据可复核的导师推荐与套磁管理项目。用户只需要提供私人材料和目标院校；Agent 负责整理画像、接入缺失院校、收集证据、运行匹配、完成质量检查并打开 Viewer。

> 真实简历、学生画像、研究结果和联系状态默认只留在本机。自动证据用于辅助判断，最终申请决策由用户确认。

## 当前项目

项目已经具备完整的确定性研究底座：

- 从学院官方目录和教师主页采集名单、方向、简介、邮箱与主页。
- 使用统一 ranking policy 输出 `强烈建议`、`可以考虑`、`暂不优先`，保留理由、方向锚点、分来源得分和警告。
- 补充 DBLP、arXiv、已知网页、官方 PDF 和可选 bounded WebSearch 证据。
- 处理同名教师、跨学院重复和多学院归属，不按研究方向猜身份或学院。
- 使用 checkpoint、run manifest 和质量审计保证中断恢复及结果可追溯。
- 在本地 Viewer 中查看四周日历、校院进度、推荐列表、教师详情和联系记录。

### 从提交材料到查看结果

<p align="center">
  <img src="docs/assets/tutor-recommendation-agent-flow.png" alt="香风智乃提交简历、确认画像、收集导师证据、完成匹配并在本地看板跟进的流程" width="1200">
</p>

整个流程都在当前项目中完成：私人材料进入本地忽略目录，正式画像必须经用户确认；Agent 如果发现目标院校尚未支持，会先增加官方目录解析、目标注册和测试，再运行匹配。

### 项目中的关键位置

```text
user_private/                  用户唯一需要关注的私人资料区
  source/                      简历、申请表、成绩单、个人说明
  profile/student_profile.json 经确认的正式画像
  request.md                   目标院校、学院和偏好

src/tutor_recommendation/      确定性采集、证据、评分和 Agent 内部工具
viewer/                        本地推荐与套磁工作台
outputs/                       本地生成结果、缓存和联系状态
docs/agent-workflow.md         Coding Agent 的完整执行规则
```

`user_private/`、`outputs/` 和 `docs/private/` 中的本地内容均受 Git 忽略规则保护。公开仓库只保留说明、模板、代码和可复用方法。

### Agent 使用的内部入口

普通用户不需要记住这些命令。Coding Agent 会使用统一入口：

```powershell
python -m pip install -e .
tutor setup
tutor profile extract
tutor profile validate
tutor targets --check <target>
tutor run <target>
tutor doctor <target>
tutor audit --fail-on-violations
tutor view
```

Windows 用户可以直接双击根目录的 `start_viewer.bat` 打开 Viewer。它会复用已经启动的当前服务；如果默认端口被旧版 Viewer 或其他程序占用，则自动选择空闲端口，不会终止旧进程或清除联系状态。旧阶段包装器保存在 `scripts/legacy/` 作为兼容实现，Agent 和新自动化统一使用 `tutor` 入口。

详细实现和运维说明：

- [Coding Agent 工作流](docs/agent-workflow.md)
- [运行手册](docs/runbook.md)
- [教师匹配方法](docs/teacher-matching-workflow.md)
- [输出目录规则](docs/output-organization.md)
- [Viewer 布局与交互](docs/viewer-integrated-layout.md)
- [WebSearch 补充层](docs/web-search-supplement.md)

## 如何使用 Coding Agent

### 第一步：提供自己的信息

把简历、申请表、成绩单或个人说明放入：

```text
user_private/source/
```

复制 [request.example.md](user_private/request.example.md) 为本地 `user_private/request.md`，填写目标学校、学院、申请方向和偏好。也可以直接在对话中告诉 Agent，不必手工填写文件。

如果目录尚未建立，只需让 Agent“初始化私人资料区”；Agent 会调用内部 `setup` 工具创建目录和画像草稿。

### 第二步：把目标告诉 Agent

推荐直接复制下面的请求：

```text
请读取 user_private/source/ 中的个人材料，为我匹配【学校】【学院】的导师。

先生成学生画像草稿，把研究方向、关键词权重和其他需要判断的内容集中给我确认。
如果目标院校尚未支持，请自行查找学院官方教师目录和教师主页，
新增 target、collector 和回归测试，再运行完整匹配、质量审计并打开 Viewer。

不要上传或提交我的私人材料，不要根据研究方向猜测教师身份或学院归属。
```

Agent 会先生成 `student_profile.draft.json`。草稿带有阻断标记，未经确认无法进入正式匹配。用户确认后，Agent 才会生成正式 `student_profile.json`。

### 第三步：让 Agent 完成剩余工作

Agent 应自动完成：

1. 检查材料和画像是否完整。
2. 检查目标 key、学校和学院是否已注册。
3. 如果目标不存在，查找官方来源并实现或复用 collector。
4. 为新增目标补充 registry 绑定和回归测试。
5. 联合构建重叠学院，执行教师身份和跨学院去重。
6. 依次运行目录/主页、DBLP、arXiv/网页证据阶段。
7. 检查 checkpoint 覆盖和 ranking policy 违规。
8. 启动 Viewer，让用户查看教师、证据和套磁进展。

遇到官网不可访问、目录范围不清、同名身份冲突或画像方向无法可靠判断时，Agent 会把证据和少量必要问题集中交给用户确认，而不是静默猜测。

### Coding Agent 必须遵守的边界

- 不提交 `user_private/` 中的真实材料、正式画像或人工 override。
- 不提交 `outputs/`、联系状态、缓存、当前教师统计或本地截图。
- 不把自动抽取的画像草稿直接用于正式匹配。
- 不让 DBLP、arXiv 或搜索关键词在缺少官方核心方向锚点时单独推高推荐等级。
- 不自动发送套磁邮件、消息或改变联系状态。
- 新院校必须使用官方教师目录或教师主页，并补充可重复验证的测试。
- 前端只展示 Python ranking policy 的结果，不在 JavaScript 中重新评分。

项目级稳定规则位于 [AGENTS.md](AGENTS.md)。在仓库根目录启动 Codex 或其他 Coding Agent 后，Agent 应先读取该文件和 [Coding Agent 工作流](docs/agent-workflow.md)，再处理私人材料或修改目标解析器。
