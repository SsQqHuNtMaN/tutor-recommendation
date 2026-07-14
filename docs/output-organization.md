# 输出目录组织

本项目的输出按“学生画像 / 学校 / 学院”归档，避免不同画像、院校的 Excel、checkpoint、cache 和联系状态混在一起。

## 目录规则

旧画像兼容目录继续使用：

```text
outputs/<school_slug>/<college_slug>/
```

命名画像统一使用：

```text
outputs/by_profile/<profile_id>/<school_slug>/<college_slug>/
```

`school_slug` 和 `college_slug` 使用短小 ASCII 名称，便于 PowerShell、Python 和跨平台工具稳定处理。例如：

- 上海交通大学：`sjtu`
- 南京大学：`nju`
- 中国人民大学：`ruc`
- 复旦大学：`fudan`
- 东南大学：`seu`
- 同济大学：`tongji`
- 浙江大学：`zju`
- 计算机学院：`cs`
- 人工智能学院：`ai`
- 高瓴人工智能学院：`gsai`
- 苏州人工智能学院：`ssai`
- 机器人与自动化学院：`ra`
- 智能科学与技术学院：`is`
- 集成电路学院：`ic`
- 智能机器人与先进制造创新学院：`ciram`
- 东南大学计算机科学与工程学院：`seu/cse`
- 东南大学软件学院：`seu/software`
- 东南大学人工智能学院：`seu/ai`
- 电子与信息工程学院：`see`
- ZJUI 联合学院：`uiuc`
- 控制科学与工程学院：`cse`
- 电子信息与电气工程学院：`seiee`
- 自动化学院：`automation`

## 根层规则

旧画像的联系状态保留在 `outputs/contact_status.json`。每个命名画像使用自己的 `outputs/by_profile/<profile_id>/contact_status.json`；它是该画像的人工状态主源，不与其他画像共享。Excel、checkpoint 和 cache 继续放在对应画像的学校/学院目录。

公开文档不记录当前本机已经生成了哪些目标、多少教师或多少证据行。这类运行状态属于本地私有交接资料，应放在 `docs/private/` 或直接从 `outputs/` 查看。

## 单个学院目录内容

每个学院目录独立保存：

```text
outputs/<school_slug>/<college_slug>/
  <school_slug>_<college_slug>_teacher_match.xlsx
  <school_slug>_<college_slug>_teacher_match_dblp.xlsx
  <school_slug>_<college_slug>_teacher_match_publications.xlsx
  <school_slug>_<college_slug>_teacher_match_full_research.xlsx
  full_research_checkpoint.jsonl
  run_manifest.json
  dblp_cache/
  math_publication_cache/
  arxiv_cache/
  web_cache/
  pdf_cache/
```

如果同一学校的多个目标在一次第一阶段命令里批量构建，脚本会在写入这些学院目录前先做跨目标去重。只有共享强身份 URL 的记录会自动合并；同校同名但缺少正身份信号时保留两行并写入人工复核备注。被合并的信息会保留在优先目标的工作簿中，并通过 `去重备注` 标明来源。显式 `cross_target_overlap_group` 用于多学院归属，组内可在官方证据支持下保留相同教师 ID 的多条学院成员关系。

可选目录：

```text
outputs/<school_slug>/<college_slug>/
  arxiv_debug/
  web_search_cache/
  web_search_debug_cache*/
  ddg_debug/
  archive/
```

`pdf_cache/` 用于缓存目标页面上的 PDF 导师库或团队介绍附件。
`arxiv_debug/` 用于保存 arXiv 异常 payload 或排查材料。`web_search_cache/` 用于保存正式 bounded web search 查询与页面缓存。`web_search_debug_cache*/` 和 `ddg_debug/` 只用于调试搜索引擎返回质量，不作为正式证据来源。`archive/` 只放旧版本、人工备份或不再由脚本直接读写的文件。

## 命名规则

Excel 文件统一使用：

```text
<school_slug>_<college_slug>_teacher_match.xlsx
<school_slug>_<college_slug>_teacher_match_dblp.xlsx
<school_slug>_<college_slug>_teacher_match_full_research.xlsx
```

示例格式：

```text
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_full_research.xlsx
```

## Agent 内部工具约定

统一入口通过目标键检查和运行：

```powershell
tutor targets --check <target>
tutor run <target>
```

目标键在 `src/tutor_recommendation/teacher_match_targets.py` 中定义。包内 DBLP 和最终补全实现仍通过环境变量接收目标上下文：

```python
SCHOOL_SLUG = os.environ.get("SCHOOL_SLUG", "sjtu")
COLLEGE_SLUG = os.environ.get("COLLEGE_SLUG", "cs")
OUTPUT_DIR = Path("outputs") / SCHOOL_SLUG / COLLEGE_SLUG
OUTPUT_PREFIX = f"{SCHOOL_SLUG}_{COLLEGE_SLUG}_teacher_match"
```

因此，绕过目标键、直接调用包内实现时需要设置：

```powershell
$env:SCHOOL_SLUG='<school_slug>'
$env:COLLEGE_SLUG='<college_slug>'
```

源码集中在 `src/tutor_recommendation/`；根目录只保留 `tutor.py` 引导入口，兼容包装器位于 `scripts/legacy/`。个人简历、申请材料和本地学生画像放在 `user_private/`，旧 `data/private/` 继续兼容，可复用画像模板放在 `data/templates/`。正式研究产物和 cache 放在 `outputs/<school_slug>/<college_slug>/`；跨学院共享的人工套磁状态固定放在 `outputs/contact_status.json`。

本地看板主入口为：

```powershell
tutor view
```

Windows 下该 bat 会启动或复用本地看板并打开网页，不会额外启动 Codex 或其他终端。

或在 Git Bash / macOS / Linux 下：

```bash
./scripts/start_viewer.sh
```

手动服务入口为：

```powershell
python tutor.py view --port 8765
```

服务会读取 `outputs/<school_slug>/<college_slug>/*_teacher_match_full_research.xlsx`，并把网页中的套磁编辑自动写入 `outputs/contact_status.json`。需要把 JSON 状态写回 Excel 时运行：

```powershell
python scripts/legacy/sync_contact_status_to_workbooks.py
```

联系状态列固定为 `套磁情况`、`套磁时间`、`回复情况`、`约面试时间`、`回复情况备注`。`约面试时间` 使用本地日期时间并精确到分钟；`套磁情况` 允许 `已套磁`、`先不考虑`、`不可能`、`不匹配`。旧 `套磁备注` 和自定义回复文本应迁移到 `回复情况备注`。

最终主表还包含稳定身份与排名审计列，例如 `教师ID`、`身份置信度`、`显式核心锚点`、`评分规则版本`、各证据分项和 `评分警告`。只有强 URL 或邮箱身份可跨阶段稳定复用；目标内 provisional ID 仍表示待复核身份。

看板会用这些结构化列直接展示套磁判断、核心匹配、教师主页方向和风险，不会重新评分。套磁日历与表格共用 `contact_status.json`，但筛选彼此独立：日历只使用自己的学校和学院选项，教师列表使用搜索、推荐等级和套磁状态等选项。日历固定在列表筛选和可折叠详情栏上方，以连续四周条带显示每天各回复状态的数量；点击日期后才列出当天教师和完整回复链。缺日期记录保留为默认折叠列表，不再生成套磁频率警告。首次选择“已套磁”且 `套磁时间` 为空时，会按本机日期补入当天；已有日期保持不变。旧工作簿缺列时页面会标记“旧数据”；要获得完整的锚点和分来源得分展示，需要按当前 policy 重跑三阶段。

## Cache 规则

cache 必须跟随学院目录，不放在 `outputs/` 根层：

- DBLP cache：`outputs/<school_slug>/<college_slug>/dblp_cache/`
- arXiv cache：`outputs/<school_slug>/<college_slug>/arxiv_cache/`
- 网页 cache：`outputs/<school_slug>/<college_slug>/web_cache/`
- PDF 附件 cache：`outputs/<school_slug>/<college_slug>/pdf_cache/`
- WebSearch cache：`outputs/<school_slug>/<college_slug>/web_search_cache/`

这样做的原因：

- 不同学院教师姓名可能重合，分学院缓存更容易审计。
- 可以单独删除某个学院的缓存，不影响其他学院。
- 断点续跑时只读取当前学院的 checkpoint。
- DBLP affiliation 关键词按学校切换，缓存和证据来源保持一致。

缓存默认有时效：DBLP 为 14 天，arXiv/已知网页和 WebSearch 为 7 天。可分别用 `DBLP_CACHE_MAX_AGE_DAYS`、`RESEARCH_CACHE_MAX_AGE_DAYS`、`WEB_SEARCH_CACHE_MAX_AGE_DAYS` 覆盖；设置为 `0` 表示本次运行不读取旧缓存。

## 可选证据列

不同目标可以在稳定基础列之外增加可审计的补充证据列。PDF 附件目标常见列包括：

- `去重备注`
- `导师信息库研究方向`
- `导师信息库团队`
- `团队PDF证据`
- `导师信息库PDF`
- `学院归属`
- `学院归属状态`
- `学院归属方式`
- `学院归属证据`
- `学院归属来源`

后续 DBLP、arXiv、网页和看板阶段应以最新工作簿行作为底稿，原样保留这些补充列。

## Checkpoint 规则

第三阶段 checkpoint 固定为：

```text
outputs/<school_slug>/<college_slug>/full_research_checkpoint.jsonl
```

最终补全阶段在汇总时以最新 DBLP 增强表为底，再叠加 checkpoint 中的 arXiv/web 证据。checkpoint 指纹包含教师 ID、关键输入证据、画像哈希、policy/schema 版本、动态年份窗口和输入哈希；任何相关变化都会使旧记录失效。`--finalize-only` 默认要求 100% 有效覆盖，可先运行 `tutor doctor <target>` 检查；`--allow-partial` 只用于明确接受缺失深检索证据的场景。

## Run Manifest

每个阶段会更新学院目录下的：

```text
outputs/<school_slug>/<college_slug>/run_manifest.json
```

manifest 按阶段记录运行 ID、画像哈希、policy/schema 版本、Git revision、动态近三年窗口和输入文件哈希。它用于审计产物来源，不替代 Excel 中的 `匹配依据` sheet。

## Archive 规则

`archive/` 只放人工备份或旧版本。当前工作流的正式输入输出应留在学院目录根层：

- 第一阶段表：`<school_slug>_<college_slug>_teacher_match.xlsx`
- DBLP 增强表：`<school_slug>_<college_slug>_teacher_match_dblp.xlsx`
- 最终综合表：`<school_slug>_<college_slug>_teacher_match_full_research.xlsx`
- checkpoint：`full_research_checkpoint.jsonl`
- 运行清单：`run_manifest.json`

不要让脚本依赖 `archive/` 里的文件。

## 新增学校或学院

推荐步骤：

1. 为学校和学院确定 slug。
2. 在 `src/tutor_recommendation/teacher_match_targets.py` 新增目标配置。
3. 在 `src/tutor_recommendation/first_pass_research.py` 实现该学院的目录页和教师主页解析。
4. 运行第一阶段，确认输出生成在 `outputs/<school_slug>/<college_slug>/`。
5. 由 Agent 运行 `tutor run <target>` 完成三阶段。
6. 运行 `tutor doctor <target>` 和 `tutor audit --fail-on-violations`。
7. 不复用其他学院 cache，除非明确知道作者、主页和来源完全一致。

## 清理规则

缓存默认保留，只有明确想重新全量抓取某个学院时才删除当前学院目录下的缓存，例如：

```powershell
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\dblp_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\arxiv_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\web_cache' -Recurse -Force
```

删除前确认路径符合：

```text
outputs/<school_slug>/<college_slug>/<cache_dir>
```

不要对 `outputs/` 根目录做递归删除。
