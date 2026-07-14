# Coding Agent 工作流

本项目采用 Agent-first 使用方式。普通用户只提供私人材料、目标院校/学院和必要确认；Coding Agent 负责调用确定性工具、补充缺失目标、运行研究流程和验收结果。

## 用户入口

第一次使用时，用户把简历、申请表、成绩单和个人说明放入：

```text
user_private/source/
```

需要维护多个学生画像时，每个画像使用独立目录：

```text
user_private/profiles/<profile_id>/source/
user_private/profiles/<profile_id>/student_profile.json
```

目标和偏好可写在忽略的 `user_private/request.md`，也可以直接通过对话提供。公开格式见 `user_private/request.example.md`。

推荐请求：

```text
请读取 user_private/source/ 中的材料，为我匹配指定学校和学院的导师。
先生成学生画像草稿供我确认。如果目标尚未支持，请自行查找官方教师目录，
添加 target、collector 和测试，再完成匹配、质量审计并打开 Viewer。
```

## Agent 执行顺序

### 1. 建立私人工作区

```powershell
tutor setup
tutor profile create <profile_id>  # 仅在新增命名画像时
tutor profile extract <profile_id>
```

`profile extract` 只做本地 PDF、DOCX、TXT、Markdown 或 JSON 文本抽取，生成 `student_profile.draft.json`。草稿带有阻断标记，不能进入正式匹配。

Agent 应根据材料提炼背景摘要、研究方向、关键词权重、同义概念组和强信号词，然后集中向用户确认。确认后移除草稿标记，保存为：

```text
user_private/profiles/<profile_id>/student_profile.json
```

不指定画像 ID 时仍使用 `user_private/profile/student_profile.json` 兼容旧工作区。

验证：

```powershell
tutor profile validate <profile_id>
tutor profile use <profile_id>
```

### 2. 检查目标支持

先从学校和学院生成简短 ASCII target key，再运行：

```powershell
tutor targets --check <target>
```

存在时继续运行。不存在时 Agent 不得让用户自行改代码，也不得静默换成相近学院。

### 3. 接入缺失院校

1. 查找学院官方教师名录、教师主页和必要的官方招生/PDF材料。
2. 在 `teacher_match_targets.py` 注册学校、学院、目录 URL、affiliation 关键词、`evidence_profile` 和论文窗口。
3. 优先复用相同站点家族的 collector；否则在 `src/tutor_recommendation/collectors/<school>.py` 实现新的目录和详情解析器，不继续扩大兼容期第一阶段文件。
4. 在 `collectors/registry.py` 使用 `tutor_recommendation.collectors.<school>:<function>` 显式绑定 target 与 collector；现有纯函数名绑定只用于尚未迁移的兼容实现。
5. 保留稳定输出列、教师身份规则、学院归属证据和跨目标去重边界。
6. 增加解析器样本或结构回归测试；避免只有实时网络测试。
7. 运行单测、编译和第一阶段小样本检查，再进行正式三阶段。

不得从研究方向推断学院归属；同名记录缺少强身份证据时保留待复核。官网不可访问、目录范围不清或多人身份冲突时，Agent 应把证据和阻塞集中交给用户确认。

### 4. 运行完整匹配

```powershell
tutor run <target> --profile <profile_id>
```

多个重叠学院应放在同一次命令中，第一阶段会联合去重，后续证据阶段逐目标执行。统一入口会按 target 自动选择 DBLP 或数学文献证据，不需要用户判断数据库。

### 5. 验收并展示

```powershell
tutor doctor <target> --profile <profile_id>
tutor audit --fail-on-violations
tutor view --profile <profile_id>
```

Agent 应报告画像是否确认、目标是否新增、官方来源、测试结果、checkpoint 覆盖和质量门禁，不在公开文档中写教师级结果或私人统计。

## 内部工具与兼容

`python -m tutor_recommendation` 和安装后的 `tutor` 是 Agent 的统一内部入口。根目录旧脚本在迁移期继续可用，确保历史自动化、checkpoint 和交接命令不被一次性重构破坏。
