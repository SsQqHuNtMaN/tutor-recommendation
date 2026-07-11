# 运行手册

本文记录公开、可复用的运行方式。个人材料、当前爬取结果、人工复核结论和联系状态都应保存在本机忽略目录中，不写入本文件。

## 1. 环境

从项目根目录运行：

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pip install -r requirements.txt
```

PDF 文本抽取：

- `PyMuPDF` / `fitz` 已列入 `requirements.txt`，用于从 PDF 简历、
  导师库或团队介绍附件中抽取文本。

快速检查：

```powershell
python -c "import pandas, openpyxl, requests, bs4, pypinyin, fitz; print('ok')"
```

## 2. 本地学生画像

公开仓库只提供占位模板。真实简历、申请表和画像放在 `data/private/`：

```powershell
Copy-Item data/templates/student_profile.example.json data/private/student_profile.json
```

也可以用环境变量指定其他画像：

```powershell
$env:STUDENT_PROFILE_PATH='D:\path\to\student_profile.json'
```

各主命令也支持：

```powershell
python build_teacher_match.py <target> --profile 'D:\path\to\student_profile.json'
python build_teacher_match.py <target> --demo-profile
```

`--profile` 和 `--demo-profile` 互斥。正式运行缺少或无法验证私有画像时会立即失败，不会自动使用公开模板。画像文件控制匹配方向、关键词权重、同义概念组、院所加分和强信号词。不要把真实画像提交到 Git。

## 3. 目标键

目标配置定义在：

```text
src/tutor_recommendation/teacher_match_targets.py
```

查看可用目标：

```powershell
python build_teacher_match.py --help
```

新增学校或学院时，先注册目标键，再在第一阶段解析器中实现目录和主页抽取逻辑。

## 4. 三阶段流程

第一阶段：抓取教师目录和主页，生成初步推荐。

```powershell
python build_teacher_match.py <target>
```

第二阶段：补充 DBLP 近三年论文证据。

```powershell
python update_teacher_match_with_dblp.py <target>
```

第三阶段：补充 arXiv 和已知网页证据，生成最终工作簿。

```powershell
python complete_teacher_research.py <target>
```

常见输出：

```text
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match.xlsx
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_dblp.xlsx
outputs/<school_slug>/<college_slug>/<school_slug>_<college_slug>_teacher_match_full_research.xlsx
```

批量跑第一阶段：

```powershell
python build_teacher_match.py --all
```

如果同一学校有多个重叠学院或多院导师库，应把这些目标放在同一条第一阶段命令里运行，这样会启用跨目标去重：

```powershell
python build_teacher_match.py zju_ai zju_cs zju_uiuc zju_cse
python build_teacher_match.py fudan_ciram fudan_ai
python build_teacher_match.py nju_cs nju_ai nju_is
```

跨目标去重只使用个人主页/教师主页强身份键。同校同名但没有共享正身份信号时保留两行并标记人工复核；目录页、登录页、实验室首页和带 `#姓名` 的列表锚点不会被当作个人身份键。

## 5. DBLP 设置

通用入口会从目标配置自动设置学校、学院和 affiliation 关键词。需要手动调用包内实现时，可设置：

```powershell
$env:SCHOOL_SLUG='<school_slug>'
$env:COLLEGE_SLUG='<college_slug>'
$env:AFFILIATION_KEYWORDS='<school affiliation keywords>'
python update_teacher_match_with_dblp.py
```

大名单目标可限制 DBLP 查询范围：

```powershell
python update_teacher_match_with_dblp.py <target> --recommendation-levels 强烈建议
```

人工 DBLP 消歧不要写进源码。复制模板到本地私有目录：

```powershell
Copy-Item data/templates/dblp_overrides.example.json data/private/dblp_overrides.json
```

脚本默认读取 `data/private/dblp_overrides.json`，也可设置：

```powershell
$env:DBLP_OVERRIDES_PATH='D:\path\to\dblp_overrides.json'
```

## 6. 第三阶段续跑

第三阶段 checkpoint 位于：

```text
outputs/<school_slug>/<college_slug>/full_research_checkpoint.jsonl
```

中断后直接重跑同一命令即可。只想用现有 checkpoint 重新汇总最终 Excel，不发起新网络请求：

```powershell
python complete_teacher_research.py <target> --finalize-only
```

`--finalize-only` 默认要求当前输入的每一行都有有效 checkpoint。先检查：

```powershell
python checkpoint_doctor.py <target>
```

只有明确接受未覆盖行缺少深检索证据时才使用 `--allow-partial`。如果第一阶段、DBLP 表、学生画像、评分规则、年份窗口或关键教师字段变化，不要只用 finalize-only；正常重跑第三阶段会忽略 stale checkpoint 并重新补查对应行。

如果第一阶段新增或更新了 PDF 附件解析列，也应正常重跑第二、三阶段。DBLP 阶段会以最新第一阶段行作为底稿，保留已有 DBLP 证据并携带新增列到后续工作簿。

## 7. 可选 WebSearch 补充层

对低证据候选做 bounded web search：

```powershell
python supplement_web_search_research.py <target>
```

只用已整理或缓存证据重写最终表：

```powershell
python supplement_web_search_research.py <target> --max-candidates 0
```

人工审核过的搜索证据可放入本地私有 JSON：

```powershell
Copy-Item data/templates/web_search_curated.example.json data/private/web_search_curated.json
```

脚本默认读取 `data/private/web_search_curated.json`，也可设置：

```powershell
$env:CURATED_WEB_SEARCH_PATH='D:\path\to\web_search_curated.json'
```

自动搜索证据只作为发现层，不直接改变排名；人工确认的中/高置信证据也只能在已有官方核心锚点时有限补强。同名论文或新闻必须用学校、主页、实验室或项目归属交叉校验。

## 8. 本地看板

推荐入口：

```powershell
.\start_viewer.bat
```

或在 Git Bash / macOS / Linux 下：

```bash
./start_viewer.sh
```

手动启动：

```powershell
python viewer_server.py --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

看板读取 `outputs/` 中的最终工作簿，支持按学校、学院、推荐等级、分数、证据状态和套磁状态筛选，也可以临时隐藏所有 `套磁情况` 非空的教师。人工编辑会写入：

```text
outputs/contact_status.json
```

主表用于快速判断：推荐等级、匹配分、`命中关键词`、教师主页提取的 `研究方向` 和 `显式核心锚点`/`评分警告` 会并列显示。官方方向在表格中最多显示三行，悬停可查看全文；详情顶部直接展示 `是否建议套磁`，随后列出各来源证据分，并把教师主页或官方材料中的方向与 DBLP、arXiv、网页、WebSearch 辅助信号分开。证据明细默认折叠，避免把论文数量误当成方向适配度。

“全部教师”视图应用完整筛选条件；“已套磁”视图只显示 `套磁情况=已套磁` 的教师，并禁用套磁状态筛选和“隐藏已标记”。后者会隐藏所有非空状态，包括 `先不考虑`、`不可能` 和 `不匹配`，不要与“已套磁”视图混用。

首次把一位教师切换为“已套磁”时，如果 `套磁时间` 为空，看板会按浏览器所在机器的本地日期自动填写当天，并默认加入回复状态“已发”。手工填写过的日期和已有回复状态不会被覆盖。

看板不在 JavaScript 中重新评分，只读取工作簿里的 policy 结果。尚未重跑的旧工作簿如果缺少 `显式核心锚点`、`评分规则版本` 或分来源得分，会标记为“旧数据”并回退显示已有证据概览；需要完整判断时应重跑三阶段，而不是在前端补推断。

需要同步回 Excel：

```powershell
python sync_contact_status_to_workbooks.py
```

`outputs/contact_status.json` 是本地编辑状态源；Excel 更适合查看、审计和交付。

看板只允许监听 `127.0.0.1`、`localhost` 或 `::1`。写接口要求当前进程的会话令牌、同源 Host/Origin、`application/json` 和 2 MiB 请求体上限；不要用 `0.0.0.0` 暴露到局域网。状态 JSON 损坏时服务会报错并拒绝静默覆盖。

启动脚本会同时检查 `/api/health` 的 API 版本和 `/api/session`。如果端口上仍是升级前的旧服务，脚本会拒绝静默复用，并提示先关闭旧进程再启动。

套磁字段：

- `套磁情况`：`已套磁`、`先不考虑`、`不可能`、`不匹配`，或留空。
- `回复情况`：固定回复选项，包含 `考核`。
- `回复情况备注`：自定义回复、原 `套磁备注` 和补充说明统一写在这里。

## 9. 最终检查

交付前建议检查：

- `全量教师名录` 行数是否符合目录解析预期。
- `优先套磁名单` 是否都能追溯到主页、DBLP、arXiv、网页或搜索证据。
- 低置信 arXiv 是否没有单独驱动 `强烈建议`。
- DBLP 歧义、未匹配或抓取失败的高价值候选是否人工看过。
- 每位推荐教师都有可读 `推荐理由`。
- 输出、cache 和 checkpoint 是否都在 `outputs/<school_slug>/<college_slug>/`。
- 对重叠学院运行跨目标重复审计：强身份 URL 不应重复；剩余同校同名项应能解释为不同人或待人工复核。
- PDF 附件目标是否生成了 `pdf_cache/`，且 `导师信息库PDF` 等来源列可回溯。
- 真实简历、画像、结果表、cache、联系状态和私有交接资料是否未被 Git 跟踪。

自动化检查：

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m unittest discover -s tests -v
python -m compileall -q .
python result_quality_audit.py --fail-on-violations
```

质量审计只读取最终工作簿并用当前 policy 影子评分，不会改写 Excel。每个阶段的新运行还会更新学院目录下的 `run_manifest.json`。

## 10. 常见问题

DBLP 抓取失败：

- 可能是限流、TLS、代理或远端断连。
- 稍后重跑第二阶段。
- 不要把 `503`、`504` 或 HTML 错误页当成有效 XML。

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
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\arxiv_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\web_cache' -Recurse -Force
Remove-Item -LiteralPath 'outputs\<school_slug>\<college_slug>\pdf_cache' -Recurse -Force
```

删除前确认路径符合：

```text
outputs/<school_slug>/<college_slug>/<cache_dir>
```

不要对 `outputs/` 根目录递归删除。
