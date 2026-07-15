# 运行手册

本文记录公开、可复用的运行方式。个人材料、当前爬取结果、人工复核结论和联系状态都应保存在本机忽略目录中，不写入本文件。

## 1. 环境

从项目根目录运行：

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pip install -e .
```

PDF 文本抽取：

- `PyMuPDF` / `fitz` 已列入 `requirements.txt`，用于从 PDF 简历、
  导师库或团队介绍附件中抽取文本。

快速检查：

```powershell
python -c "import pandas, openpyxl, requests, bs4, pypinyin, fitz; print('ok')"
```

## 2. Agent 私人资料与学生画像

单画像兼容入口是 `user_private/source/`；多个学生或申请方向使用 `user_private/profiles/<profile_id>/source/`。Coding Agent 建立工作区并抽取草稿：

```powershell
tutor setup
tutor profile extract
```

草稿位于 `user_private/profile/student_profile.draft.json`，带有确认阻断标记。Agent 必须让用户确认背景摘要、关键词权重、同义概念组、可选方向分组、院所加分和强信号词，再保存为 `user_private/profile/student_profile.json` 并运行：

```powershell
tutor profile validate
```

需要为不同申请方向建立独立画像时使用命名画像：

```powershell
tutor profile create math-ai --display-name "数学 × AI"
tutor profile extract math-ai
tutor profile validate math-ai
tutor profile use math-ai
tutor profile list
```

命名画像材料位于 `user_private/profiles/<profile_id>/`，结果和联系状态位于 `outputs/by_profile/<profile_id>/`。Viewer 标题栏可手动切换；切换不会把另一画像的工作簿或联系状态加载进来。

也可以用环境变量指定其他画像：

```powershell
$env:STUDENT_PROFILE_PATH='D:\path\to\student_profile.json'
```

统一入口也支持：

```powershell
tutor run <target> --profile <profile_id-or-json-path>
tutor run <target> --demo-profile
```

`--profile` 和 `--demo-profile` 互斥。正式运行缺少或无法验证私有画像时会立即失败，不会自动使用公开模板。画像文件控制匹配方向、关键词权重、同义概念组、方向分组、院所加分和强信号词。`direction_term_groups` 只能引用已有正权重词，同一个词不能跨组重复。不要把真实画像提交到 Git。

画像权重、alias 或方向分组变化会改变 profile hash，使旧 checkpoint 失效。更新已确认画像后应正常运行 `tutor run <target> --profile <profile_id>` 重建三个阶段，再用 doctor 验证；不要只执行 `--finalize-only`。

## 3. 目标键

目标配置定义在：

```text
src/tutor_recommendation/teacher_match_targets.py
```

查看可用目标：

```powershell
tutor targets
tutor targets --check <target>
```

目标不存在时，Coding Agent 应按 [Agent 工作流](agent-workflow.md) 查找官方目录、注册 target、实现或复用 collector、绑定 registry 并补测试，而不是让用户自行改代码。

## 4. 三阶段流程

Agent 的常规入口会依次运行目录/主页、学科论文证据、arXiv/网页三个阶段。`tutor run` 根据 target 的 `evidence_profile` 自动选择 DBLP 或数学文献适配器：

```powershell
tutor run <target>
```

兼容包装器位于 `scripts/legacy/`，只用于高级参数和排障：

```powershell
python scripts/legacy/build_teacher_match.py <target>
python scripts/legacy/update_teacher_match_with_dblp.py <target>
python scripts/legacy/update_teacher_match_with_math_publications.py <target>
python scripts/legacy/complete_teacher_research.py <target>
```

常见输出：

```text
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match.xlsx
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_dblp.xlsx
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_publications.xlsx
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_full_research.xlsx
```

命名画像把同一结构放在 `outputs/by_profile/<profile_id>/` 下。数学目标的第二阶段文件使用 `_publications.xlsx`，并包含 canonical `数学文献近五年明细`、`学术作者候选` 和 `论文来源报告`。第二阶段会为所有教师执行有界身份候选发现，但只对画像候选或中高置信作者拉取 works；作者身份未达到中高置信度或缺少官方方向锚点时，论文命中不能改变推荐等级。DOI、arXiv ID、来源稳定 ID及受作者/年份约束的题名用于跨库合并，预印本与正式版只计一篇。

如果同一学校有多个重叠学院或多院导师库，应把这些目标放在同一条第一阶段命令里运行，这样会启用跨目标去重：

```powershell
tutor run zju_ai zju_cs zju_uiuc zju_cse
tutor run fudan_ciram fudan_ai
tutor run nju_cs nju_ai nju_is
tutor run seu_cse seu_software seu_ai
```

跨目标去重只使用个人主页/教师主页强身份键。同校同名但没有共享正身份信号时保留两行并标记人工复核；目录页、登录页、实验室首页和带 `#姓名` 的列表锚点不会被当作个人身份键。显式配置为同一 `cross_target_overlap_group` 的目标例外：如果官方证据表明导师确实属于多个学院，则保留相同稳定教师 ID 的多条学院成员关系，而不是删除其中一条。

东南大学三学院归属的本地人工复核文件为：

```text
user_private/overrides/seu_college_affiliations.json
```

可从 `data/templates/seu_college_affiliations.example.json` 复制。学院归属只能来自官方导师名单、招生材料、教师主页或人工确认记录，不得按研究方向猜测；证据不足时保留为待复核。

## 5. DBLP 设置

通用入口会从目标配置自动设置学校、学院和 affiliation 关键词。需要手动调用包内实现时，可设置：

```powershell
$env:SCHOOL_SLUG='<school_slug>'
$env:COLLEGE_SLUG='<college_slug>'
$env:AFFILIATION_KEYWORDS='<school affiliation keywords>'
python scripts/legacy/update_teacher_match_with_dblp.py
```

大名单目标可限制 DBLP 查询范围：

```powershell
python scripts/legacy/update_teacher_match_with_dblp.py <target> --recommendation-levels 强烈建议
```

人工 DBLP 消歧不要写进源码。复制模板到本地私有目录：

```powershell
Copy-Item data/templates/dblp_overrides.example.json user_private/overrides/dblp_overrides.json
```

脚本优先读取 `user_private/overrides/dblp_overrides.json`，并兼容旧 `data/private/` 路径；也可设置：

```powershell
$env:DBLP_OVERRIDES_PATH='D:\path\to\dblp_overrides.json'
```

## 6. 第三阶段续跑

第三阶段 checkpoint 位于：

```text
<profile_root>/<school_slug>/<college_slug>/full_research_checkpoint.jsonl
```

其中 `<profile_root>` 是旧画像的 `outputs/`，或命名画像的 `outputs/by_profile/<profile_id>/`。

中断后直接重跑同一命令即可。只想用现有 checkpoint 重新汇总最终 Excel，不发起新网络请求：

```powershell
python scripts/legacy/complete_teacher_research.py <target> --finalize-only
```

`--finalize-only` 默认要求当前输入的每一行都有有效 checkpoint。先检查：

```powershell
tutor doctor <target>
```

只有明确接受未覆盖行缺少深检索证据时才使用 `--allow-partial`。如果第一阶段、第二阶段论文证据表、学生画像、评分规则、论文窗口或关键教师字段变化，不要只用 finalize-only；正常重跑第三阶段会忽略 stale checkpoint 并重新补查对应行。

如果第一阶段新增或更新了 PDF 附件解析列，也应正常重跑第二、三阶段。第二阶段会以最新第一阶段行作为底稿，保留已有学科论文证据并携带新增列到后续工作簿。

## 7. 可选 WebSearch 补充层

对低证据候选做 bounded web search：

```powershell
python scripts/legacy/supplement_web_search_research.py <target>
```

只用已整理或缓存证据重写最终表：

```powershell
python scripts/legacy/supplement_web_search_research.py <target> --max-candidates 0
```

人工审核过的搜索证据可放入本地私有 JSON：

```powershell
Copy-Item data/templates/web_search_curated.example.json user_private/overrides/web_search_curated.json
```

脚本优先读取 `user_private/overrides/web_search_curated.json`，并兼容旧 `data/private/` 路径；也可设置：

```powershell
$env:CURATED_WEB_SEARCH_PATH='D:\path\to\web_search_curated.json'
```

自动搜索证据只作为发现层，不直接改变排名；人工确认的中/高置信证据也只能在已有官方核心锚点时有限补强。同名论文或新闻必须用学校、主页、实验室或项目归属交叉校验。

## 8. 本地看板

推荐入口：

```powershell
tutor view
```

Windows 一键入口是仓库根目录的 `start_viewer.bat`，可以直接双击。启动器会复用已运行的当前 Viewer；默认端口被旧版 Viewer 或其他程序占用时，会自动选择后续空闲端口并打开正确地址，不会关闭旧进程或删除联系状态。

或在 Git Bash / macOS / Linux 下：

```bash
./scripts/start_viewer.sh
```

手动启动：

```powershell
python tutor.py view --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

看板读取当前所选画像的最终工作簿。标题栏的“学生画像”下拉框可在运行期间手动切换；切换会重新加载教师、筛选、日历、详情和联系状态，不会回退到其他画像。教师列表支持按学校、学院、推荐等级、证据状态和套磁状态筛选，也可以临时隐藏所有 `套磁情况` 非空的教师。人工编辑写入该画像自己的：

```text
<profile_root>/contact_status.json
```

主表用于快速判断：推荐等级、匹配分、`命中关键词`、教师主页提取的 `研究方向` 和 `显式核心锚点`/`评分警告` 会并列显示。官方方向在表格中最多显示三行，悬停可查看全文；详情顶部直接展示 `是否建议套磁`，随后列出各来源证据分，并把 `画像方向分组`、教师主页方向与 DBLP 或数学文献、AI 交叉、arXiv、网页和 WebSearch 辅助信号分开。证据明细默认折叠，避免把论文数量误当成方向适配度。

“查看已套磁”只显示 `套磁情况=已套磁` 的教师。“隐藏已标记”会隐藏所有非空状态，包括 `已套磁`、`先不考虑`、`不可能` 和 `不匹配`；同时启用两个相反筛选时结果为空。

“套磁日历”固定在教师列表筛选与工作区上方，并有独立的学校、学院筛选和重置入口；搜索、推荐等级、套磁情况、“查看已套磁”和“隐藏已标记”等列表选项不会改变日历。日历以连续四周、每周一行的条带展示，星期一至星期日是固定列头，四行按本周、上周、下周等相对名称显示。每个日期只显示 `已发`、`官回`、`添加微信`、`约面试`、`考核`、`已满` 或 `未记录` 的颜色和数量；顶部图例汇总当前四周数量。点击日期后，下方列出当天教师、学校、学院、完整回复链和具体面试时间，点击教师继续打开详情。可用“上一周、本周、下一周”导航，每次移动一周。详情中勾选“约面试”后会出现精确到分钟的时间输入；日历用菱形标记已确定时间的面试。缺少 `套磁时间` 的已套磁记录保留在默认折叠列表中。日历开合三角位于标题行内；详情栏使用带顶部三角的内嵌窄控制列，二者均不向内容区凸出。顶部不再提供刷新、保存、同步、下载或导出按钮，联系编辑通过本地 API 自动保存，需要同步 Excel 时由 Agent 运行 `python scripts/legacy/sync_contact_status_to_workbooks.py`。

教师列表的“重置筛选”会显示当前活动条件数量；无匹配结果时表格提供清除入口。教师行可用 Tab 聚焦，并通过 Enter 或 Space 打开详情。日历重置只清除日历学校和学院，不改变教师列表条件。浏览器会恢复学校、学院、推荐等级、套磁状态和复选条件等非敏感筛选偏好，但不会保存搜索词、教师 ID 或联系内容。

日历右侧辅助栏的“查看学校 / 学院进度”默认折叠，按当前日历校院筛选汇总教师记录、已套磁、有进展和面试数量；点击该入口即可展开六列表格。它读取当前联系状态，不受四周日期范围限制，也不会创建新的状态源。多学院教师按学院成员关系分别计数。

详情顶部可在当前筛选结果中切换上一位或下一位教师，也可使用 `Alt+↑` / `Alt+↓`；编辑输入框、选择框或备注时快捷键自动停用。“快速定位”可跳转到套磁判断、计分构成、方向判断、套磁记录、补充信息、链接或证据明细。

完整布局与交互约定见 [Viewer 整合布局](viewer-integrated-layout.md)。

首次把一位教师切换为“已套磁”时，如果 `套磁时间` 为空，看板会按浏览器所在机器的本地日期自动填写当天，并默认加入回复状态“已发”。手工填写过的日期和已有回复状态不会被覆盖。

看板不在 JavaScript 中重新评分，只读取工作簿里的 policy 结果。尚未重跑的旧工作簿如果缺少 `显式核心锚点`、`评分规则版本` 或分来源得分，会标记为“旧数据”并回退显示已有证据概览；需要完整判断时应重跑三阶段，而不是在前端补推断。

需要同步回 Excel：

```powershell
python scripts/legacy/sync_contact_status_to_workbooks.py
```

所选画像的 `<profile_root>/contact_status.json` 是本地编辑状态源；Excel 更适合查看、审计和交付。

看板只允许监听 `127.0.0.1`、`localhost` 或 `::1`。写接口要求当前进程的会话令牌、同源 Host/Origin、`application/json` 和 2 MiB 请求体上限；不要用 `0.0.0.0` 暴露到局域网。状态 JSON 损坏时服务会报错并拒绝静默覆盖。

启动脚本会同时检查 `/api/health` 的 API 版本和 `/api/session`。如果端口上仍是升级前的旧服务，脚本会拒绝静默复用，并提示先关闭旧进程再启动。

套磁字段：

- `套磁情况`：`已套磁`、`先不考虑`、`不可能`、`不匹配`，或留空。
- `回复情况`：固定回复选项，包含 `考核`。
- `回复情况备注`：自定义回复、原 `套磁备注` 和补充说明统一写在这里。
- `约面试时间`：仅在选择“约面试”后填写，使用浏览器本地时间并精确到分钟。

## 9. 最终检查

交付前建议检查：

- `全量教师名录` 行数是否符合目录解析预期。
- `优先套磁名单` 是否都能追溯到主页、学科论文、arXiv、网页或搜索证据。
- 低置信 arXiv 是否没有单独驱动 `强烈建议`。
- 学术作者歧义、未匹配或抓取失败的高价值候选是否人工看过。
- 每位推荐教师都有可读 `推荐理由`。
- 输出、cache、checkpoint 和联系状态是否都位于同一画像根目录。
- 对重叠学院运行跨目标重复审计：普通目标的强身份 URL 不应重复；显式 overlap group 中保留的重复应有多学院归属证据；剩余同校同名项应能解释为不同人或待人工复核。
- PDF 附件目标是否生成了 `pdf_cache/`，且 `导师信息库PDF` 等来源列可回溯。
- 真实简历、画像、结果表、cache、联系状态和私有交接资料是否未被 Git 跟踪。

自动化检查：

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m unittest discover -s tests -v
python -m compileall -q .
tutor audit --fail-on-violations
```

质量审计只读取最终工作簿并用当前 policy 影子评分，不会改写 Excel。每个阶段的新运行还会更新学院目录下的 `run_manifest.json`。

## 10. 常见问题

DBLP 抓取失败：

- 可能是限流、TLS、代理或远端断连。
- 稍后重跑第二阶段。
- 不要把 `503`、`504` 或 HTML 错误页当成有效 XML。

数学文献证据缺失：

- 先检查官方 publication list 和 zbMATH 状态；`no_candidate` 只是没有找到作者候选，`no_recent_record` 才表示已确认作者在当前窗口无记录，二者都保持中性。
- OpenAlex 是可选身份补充，需要时在本地设置 `$env:OPENALEX_API_KEY='...'`，不要把 key 写入文件。
- 只有姓名、没有机构、ORCID 或官网题名交叉确认的作者候选保持待复核。
- 需要人工确认 source ID 时，复制 `data/templates/publication_identity_overrides.example.json` 到 `user_private/overrides/publication_identity_overrides.json`，按稳定 `teacher_id` 填写并保留证据说明。
- `terms_required`、`request_failed`、`schema_changed` 或来源报告中的 `degraded/截断` 表示来源没有完整运行，不能解释为作者没有论文；修复配置或稍后重跑该阶段。
- 使用 `tutor doctor <target>` 核对空题名、canonical 重复、追溯缺失、作者复核队列和来源状态；不要只看主表论文数量判断抓取是否成功。

arXiv 命中过多：

- 常见英文名会带来同名噪声。
- 降低 arXiv 权重，只把低置信结果当线索。

checkpoint doctor 显示 missing/stale：

- 上游工作簿、画像、policy/schema、年份窗口或关键教师字段已经变化。
- 正常重跑第三阶段；不要为了绕过校验直接修改 fingerprint。

需要强制刷新缓存：

- `DBLP_CACHE_MAX_AGE_DAYS` 默认 14 天。
- `RESEARCH_CACHE_MAX_AGE_DAYS` 和 `WEB_SEARCH_CACHE_MAX_AGE_DAYS` 默认 7 天。
- 将对应值设为 `0` 可在该次运行中禁用旧缓存读取。

网页证据少但方向相关：

- 先确认 `个人主页` 和 `教师主页链接` 是否为空或过旧。
- 需要主动发现新闻、项目页或外部主页时，再跑 bounded web search。

中文命令输出乱码：

```powershell
$env:PYTHONIOENCODING='utf-8'
```

Excel 写入失败：

- 检查目标文件是否正在被 Excel 打开。
- 关闭后重跑。

## 11. 清理

缓存默认保留，便于复现和断点续跑。明确要重新全量抓取某个学院时，只删除当前学院目录下的缓存：

```powershell
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\dblp_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\math_publication_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\arxiv_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\web_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\pdf_cache' -Recurse -Force
```

删除前确认路径符合：

```text
<profile_root>/<school_slug>/<college_slug>/<cache_dir>
```

不要对 `outputs/` 根目录递归删除。
