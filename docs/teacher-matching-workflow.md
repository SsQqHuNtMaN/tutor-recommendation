# 教师匹配工作流方法论

本文说明 Tutor Recommendation 的可迁移工作流。命令级执行见 [runbook.md](runbook.md)，输出目录规则见 [output-organization.md](output-organization.md)。

## 1. 目标

给定一份本地学生画像和一个学院教师目录，产出可审计的教师推荐工作簿：

- 覆盖目标目录中的教师。
- 提取姓名、职称、邮箱、教师主页、个人主页、研究方向和简介。
- 按目标学科补充论文证据：计算机目标使用 DBLP，数学/统计目标使用官网 publication list、zbMATH Open 和可选 OpenAlex；arXiv、已知网页和可选 WebSearch 继续作为辅助。
- 输出 `强烈建议`、`可以考虑`、`暂不优先`。
- 为推荐结论保留可读理由和证据来源。

脚本负责整理证据、减少重复劳动；真正联系导师前仍应人工复核。

## 2. 学生画像

公开仓库不内置真实申请者画像。单画像兼容入口仍是 `user_private/source/`；多画像使用 `user_private/profiles/<profile_id>/source/`。Coding Agent 生成草稿并让用户确认：

```powershell
tutor setup
tutor profile extract
tutor profile validate
tutor profile list
tutor profile use <profile_id>
```

画像 JSON 建议包含：

- `resume_match_context`：简短背景摘要。
- `keyword_weights`：关键词和权重。
- `institute_bonus`：院所、实验室或方向单位加分。
- `high_signal_terms`：足以触发强相关判断的核心词。
- `concept_alias_groups`：中文、英文、缩写等同义概念组；同组命中只计一次。
- `excluded_terms`：明确不考虑的方向；命中时给出警告，没有更高优先级官方锚点时不得进入推荐名单。

如果目标画像聚焦具身智能、具身操作或机器人操作，应把 LLM、NLP、信息检索、通用多模态和 Agent 类词设为低权重或零权重。宽泛 AI 词不能替代明确的机器人、操作、抓取、触觉、VLA 等方向证据。

`--profile` 同时接受已注册的画像 ID 和 JSON 路径。显式参数优先，其次是本地 `active_profile.json`，再回退到旧画像兼容路径。命名画像的工作簿、checkpoint、manifest、cache 和联系状态统一放在 `outputs/by_profile/<profile_id>/`；切换画像不会覆盖另一画像。草稿未确认、正式画像缺失、JSON 损坏、字段类型错误或核心词没有正权重时都会立即失败；公开模板只能通过 `--demo-profile` 显式启用。

## 3. 目标注册

每个学院目标通过目标键运行。目标配置位于：

```text
src/tutor_recommendation/teacher_match_targets.py
```

目标配置应包含：

- 学校和学院 slug。
- 学校和学院展示名。
- 教师目录 URL。
- DBLP affiliation 关键词。
- `evidence_profile`：`computer_science`、`mathematics` 或 `mathematics_ai`。
- `publication_window_years`：该目标的论文证据窗口。
- 输出目录和文件前缀。

新增目标后，在 `src/tutor_recommendation/collectors/` 中实现或复用目录/主页解析逻辑，并在 `collectors/registry.py` 建立显式绑定。兼容期 `first_pass_research.py` 只负责编排和尚未迁移的旧解析器。缺失目标由 Coding Agent 按 [Agent 工作流](agent-workflow.md) 接入并补测试。

## 4. 第一阶段：目录与主页

入口：

```powershell
tutor run <target>
```

第一阶段负责：

- 识别目录加载方式：静态 HTML、分页、异步 API 或嵌入 JSON。
- 抓取教师列表和详情页 URL。
- 解析教师主页正文。
- 对提供 PDF 导师库或团队介绍附件的目标，下载附件到当前学院
  `pdf_cache/`，用文本层抽取方向、团队和来源证据。
- 抽取邮箱、个人主页、研究方向、简介和单位分类。
- 使用学生画像关键词做初步打分。

基础列建议保持稳定：

- `名录序号`
- `姓名`
- `教师ID`
- `身份置信度`
- `套磁情况`、`套磁时间`、`回复情况`、`约面试时间`、`回复情况备注`
- `职称`
- `研究所` 或 `分类`
- `邮箱`
- `教师主页链接`
- `个人主页`
- `研究方向`
- `个人简介摘要`
- `推荐等级`
- `是否建议套磁`
- `匹配分`
- `命中关键词`
- `推荐理由`
- `去重备注`
- 可选多学院模型列：`学院归属`、`学院归属状态`、`学院归属方式`、`学院归属证据`、`学院归属来源`

稳定列名能让 DBLP、arXiv、WebSearch 和本地看板复用同一套后续流程。

目标若有 PDF 补充源，可增加以下列，并在后续阶段原样保留：

- `导师信息库研究方向`
- `导师信息库团队`
- `团队PDF证据`
- `导师信息库PDF`

### 跨目标去重

同一学校的多个学院、研究院或导师库经常会重复收录同一位老师。重叠目标应在同一次第一阶段命令里批量构建，例如：

```powershell
tutor run zju_ai zju_cs zju_uiuc zju_cse
tutor run seu_cse seu_software seu_ai
```

批量构建会先分别抓取各目标，再按目标优先级做跨目标去重。去重规则：

- 优先使用 `个人主页`、`教师主页链接` 中的强身份 URL。
- 学校首页、学院列表页、统一登录页、实验室首页、带 `#姓名` 的目录锚点等只作为证据，不作为身份键。
- 不在同一个目标内按姓名合并，避免把同名老师误合并。
- 不同目标之间只有共享强身份 URL 才自动合并；同校同名但缺少正身份信号时两行都保留，并写入待人工复核备注。
- 明确配置为同一 `cross_target_overlap_group` 的目标用于真实多学院归属：共享强身份的导师在官方归属证据支持下可保留在多个目标，并共享稳定教师 ID。
- 学院归属只使用官方导师名单、招生材料、教师主页或人工复核记录；不按研究方向推断，证据不足时标记待复核。
- 被合并到保留行的来源会写入 `去重备注`。

## 5. 主页解析原则

教师主页格式差异很大，解析时优先保证可审计：

- 优先抽取正文区域，避免页眉、页脚和导航污染。
- 研究方向优先来自明确标题，如“研究方向”“研究兴趣”“Research Interests”。
- 个人主页应过滤学校首页、办公系统、论文检索页和公共导航。
- 如果没有独立个人主页，可以把官方教师主页作为证据 URL。
- 不能确定的信息宁可留空，不要伪造。

## 6. PDF 附件证据

部分学院会在导师团队信息页提供 PDF 导师库、实验室介绍或团队介绍表。处理原则：

- 优先使用 `PyMuPDF` / `fitz` 抽取 PDF 文本层。
- PDF 是扫描件或文本层过少时，记录状态，不把空文本当作证据。
- 教师级导师库可补充研究方向、团队和邮箱等字段。
- 团队 PDF 应作为团队级工作内容证据，按教师姓名或团队名谨慎映射。
- PDF 证据应保留来源 URL，方便人工复核。
- PDF 方向可以参与第一阶段打分，但仍需结合主页、学科论文、arXiv 和网页证据判断。

## 7. DBLP 证据

入口：

```powershell
python scripts/legacy/update_teacher_match_with_dblp.py <target>
```

DBLP 阶段负责：

1. 从中文姓名生成英文候选。
2. 查询 DBLP author API。
3. 按姓名、affiliation、主页重合和人工 override 消歧。
4. 抓取 DBLP person XML。
5. 保留近三年论文。
6. 用学生画像关键词给题目和 venue 打分。

人工 override 放在本地私有文件：

```text
user_private/overrides/dblp_overrides.json
```

公开模板：

```text
data/templates/dblp_overrides.example.json
```

只有高置信 DBLP 作者匹配可以参与排名，并且仍要求官方方向锚点。仅 affiliation 相符、全局姓名 override 或候选间差距不足时保持中/低置信，只作辅助并要求人工复核。

## 8. 数学与统计论文证据

`mathematics` 和 `mathematics_ai` target 使用来源中立的第二阶段：

```powershell
python scripts/legacy/update_teacher_match_with_math_publications.py <target>
```

证据优先级是官方 publication list、zbMATH Open、可选 OpenAlex。官方页面提供身份与方向锚点；开放数据库用于补全配置窗口内的题名、年份、DOI、MSC/topic 和来源。作者必须通过 ORCID、机构、官网题名/DOI 重合等信号达到中高置信；只有姓名的候选不计分。数据库无记录保持中性，引用数、h-index 和论文数量不直接参与推荐。

`mathematics_ai` 额外区分数学/统计核心匹配和 AI 交叉证据。宽泛数学词不能制造 AI 桥接，论文证据也不能绕过官方方向锚点。OpenAlex 只在本地配置 `OPENALEX_API_KEY` 时启用，key 不写入工作簿、manifest 或仓库。

## 9. arXiv 与已知网页证据

入口：

```powershell
python scripts/legacy/complete_teacher_research.py <target>
```

该阶段负责：

- 查询 target 配置的论文窗口内 arXiv 记录。
- 标注 arXiv 置信度。
- 抓取已解析出的个人主页或实验室主页。
- 无个人主页时回退抓取官方教师主页。
- 合并主页、target 第二阶段论文、arXiv 和网页证据。

arXiv 同名噪声高，只能作为辅助。只有与已确认学术作者、机构或论文题目交叉验证的记录才可达到中置信；按姓名和方向相似得到的结果保持低置信，不能单独改变推荐等级。

## 10. 可选 WebSearch 补充

入口：

```powershell
python scripts/legacy/supplement_web_search_research.py <target>
```

WebSearch 适用于低证据候选的二次发现：

- 发现近期新闻、项目页、实验室页或外部个人主页。
- 增强已有方向线索。
- 找出主页长期不更新造成的低估候选。

采信时必须交叉校验姓名、学校、主页或实验室归属。自动 WebSearch 是发现层，不直接改变排名；只有人工确认的中/高置信来源才能在已有官方核心锚点时提供有限补强。

人工整理证据放在：

```text
user_private/overrides/web_search_curated.json
```

更完整的触发条件、采信边界和输出字段见 [WebSearch 补充层说明](web-search-supplement.md)。

## 11. 综合推荐

所有阶段调用同一个 ranking policy，采集模块不再各自维护等级阈值。当前统一门槛为 `可以考虑 >= 24`、`强烈建议 >= 44`，且两者都必须先满足官方显式核心锚点。推荐等级由多类证据综合而来：

- 教师主页：基础方向证据。
- PDF 导师库或团队介绍：可审计的附件方向和团队证据。
- 学科论文：计算机目标使用 DBLP；数学/统计目标使用官方列表、zbMATH 和可选 OpenAlex。
- arXiv：辅助预印本证据。
- 已知网页：个人、实验室、新闻或项目线索。
- WebSearch：自动结果只发现来源，人工确认后才可有限补强。

规则：

- 分数用于排序，不替代推荐理由。
- 推荐等级必须有显式方向锚点：教师主页、官方名录、导师信息库 PDF 或团队 PDF 中出现学生画像的核心方向。
- 学科论文、arXiv、网页和 WebSearch 可以补强证据，但缺少显式方向锚点时不能单独把候选抬进优先名单。
- LLM、NLP、信息检索、通用多模态和 Agent 类命中只按画像权重计分；默认不应作为具身操作方向的加分项。
- 强推荐应有可靠核心证据。
- 方向相关但证据弱的候选进入 `可以考虑` 或待复核。
- 只有低置信同名证据时保持保守。
- 每条推荐都应能追溯到证据列。

工作簿会写入 `评分规则版本`、`显式核心锚点`、各证据分项和 `评分警告`，便于判断分数来自哪里。`教师ID` 用强身份 URL、邮箱或目标内临时身份生成；临时 ID 不应被当作跨目标同一人的证明。

## 12. 运行可复现性

每个学院目录的 `run_manifest.json` 按阶段记录：

- 画像 ID、画像哈希与是否 demo。
- evidence profile 与配置的论文窗口。
- ranking policy 和数据 schema 版本。
- Git revision 和输入文件哈希。
- 运行 ID 与生成时间。

第三阶段 checkpoint 的指纹同时包含教师 ID、关键输入证据、画像哈希、policy/schema 版本、年份窗口和输入哈希。旧规则、旧画像或上游工作簿变化后，旧 checkpoint 会失效；`--finalize-only` 默认要求 100% 有效覆盖，只有明确接受缺失行时才使用 `--allow-partial`。

## 13. Excel 与看板

最终工作簿通常包含：

- `优先套磁名单`
- `全量教师名录`
- `DBLP近三年明细`
- `数学文献近五年明细`（数学/统计 target）
- `arXiv近三年明细`
- `网页证据明细`
- 可选 `WebSearch证据明细`
- `匹配依据`

本地看板读取所选画像根目录中的最终工作簿，并把人工联系状态写入同一画像的：

```text
<profile_root>/contact_status.json
```

JSON 是本地编辑状态源；Excel 是查看和交付产物。

看板直接消费工作簿中的 policy 输出，不在前端重新计算推荐。标题栏可手动切换画像；每个数据、详情和联系请求都显式绑定画像 ID。详情将官方方向与画像命中、DBLP 或数学文献、AI 交叉、arXiv、已知网页和 WebSearch 信号分层展示。旧工作簿缺少结构化字段时只标记为旧数据，不从论文数量推断新结论。

套磁日历固定在教师列表筛选和详情栏上方，三者共用教师 ID、选择状态和 `contact_status.json`，但日历的学校/学院筛选与教师列表筛选相互独立。日历使用连续四周条带，星期为固定列头，周行按当前周相对命名，每次前后移动一周。每个日期只展示各回复状态的颜色和数量；已安排具体面试时间时增加菱形标记，点击日期后显示当天教师、完整回复链和面试时间，再点击教师进入同一详情。缺日期记录默认折叠，不生成同校或同学院套磁频率警告。日期、回复或面试时间编辑成功后立即刷新四周统计和当天教师列表。

看板只监听 loopback，写接口要求进程级会话令牌、同源 Host/Origin 和 JSON 请求体限制。损坏的 `contact_status.json` 会显式报错，不会被当作空状态静默覆盖。

套磁字段约定：

- `套磁情况` 可为空，或为 `已套磁`、`先不考虑`、`不可能`、`不匹配`。
- `回复情况` 使用固定选项，如 `已发`、`官回`、`添加微信`、`约面试`、`考核`、`已满`。
- 自定义回复和原 `套磁备注` 内容合并到 `回复情况备注`。
- 看板里的“隐藏已标记”会隐藏所有 `套磁情况` 非空的教师，不只隐藏 `已套磁`。

## 14. 质量检查

交付前检查：

- 教师行数是否符合目录解析预期。
- 强推荐是否有可靠官方方向锚点和可追溯证据。
- PDF 附件解析是否保留来源 URL，且没有把办公地点、页眉页脚误当成方向。
- 低置信 arXiv 是否没有单独改变推荐等级。
- 学术作者歧义候选是否人工看过。
- 每位候选是否有清晰推荐理由。
- 输出、cache、checkpoint 和联系状态是否位于同一画像根目录。

可用以下命令做聚合质量门禁，命令只影子评分，不改写现有 Excel：

```powershell
tutor audit --fail-on-violations
```

它会检查优先项是否缺少官方锚点、推荐理由或教师 ID。checkpoint 覆盖可用 `tutor doctor <target>` 检查。

## 15. 隐私边界

以下内容不进入公开仓库：

- 简历、申请表和学生画像。
- 当前运行生成的 Excel、cache、checkpoint。
- 各画像根目录中的 `contact_status.json`。
- 当前爬取结果规模、教师级证据和人工复核结论。
- 本地阶段交接和私有调研记录。

需要保留这些内容时，使用 `user_private/`、`outputs/` 或 `docs/private/`；旧 `data/private/` 只作为兼容路径。
