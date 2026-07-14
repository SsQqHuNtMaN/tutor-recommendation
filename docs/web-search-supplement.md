# WebSearch 补充层说明

本文说明 bounded web search 的通用使用边界。具体抽样名单、教师级证据和人工结论属于本地私有研究资料，应放在 `docs/private/` 或 `user_private/overrides/web_search_curated.json`，不要提交到公开仓库。

## 适用场景

WebSearch 只适合作为低证据候选的二次发现层，不能替代教师主页、目标学科的主要论文证据（DBLP 或数学文献）、arXiv 和已知网页抓取。

适合补查的候选通常满足：

- 主页或简介有相关方向线索，但 DBLP/arXiv/网页证据很少。
- 个人主页为空，官方教师主页又比较简略。
- 推荐等级较低但匹配分处在可复核区间。
- 需要确认近期新闻、项目公示、实验室页或外部个人主页。

## 采信规则

优先采信：

- 学校、学院、实验室或个人主页。
- DBLP、arXiv、ACL Anthology、OpenReview、IEEE、ACM 等论文页。
- 会议官网、项目主页、GitHub 项目页或科研项目公示。

必须交叉校验：

- 姓名。
- 学校或单位。
- 主页、实验室、项目归属或论文作者身份。

不要自动采信：

- 只有同名作者、无单位信息的论文。
- 搜索摘要里的不完整片段。
- 与目标教师无明确归属关系的新闻或项目页。
- 无法访问、无法复核或来源不稳定的网页。

## 脚本入口

```powershell
python scripts/legacy/supplement_web_search_research.py <target>
```

只使用已整理或缓存证据重写最终表：

```powershell
python scripts/legacy/supplement_web_search_research.py <target> --max-candidates 0
```

人工整理过的 curated evidence 使用本地私有 JSON：

```powershell
Copy-Item data/templates/web_search_curated.example.json user_private/overrides/web_search_curated.json
```

也可以指定路径：

```powershell
$env:CURATED_WEB_SEARCH_PATH='D:\path\to\web_search_curated.json'
```

## 输出字段

脚本会向最终表补充：

- `WebSearch状态`
- `WebSearch置信度`
- `WebSearch证据条数`
- `WebSearch关键词`
- `WebSearch代表证据`
- `WebSearch来源URL`
- `WebSearch建议`

并可增加 sheet：

- `WebSearch证据明细`

自动明细只应保留中/高置信证据。低置信同名噪声可以记录为“已搜索但无可靠补充”，但不应进入证据明细。自动 WebSearch 无论置信度如何都不直接改变推荐等级。

## 推荐更新原则

- 自动搜索证据只用于发现和排队人工复核。
- 人工确认的中/高置信来源可以在已有官方核心方向锚点时提供有限补强。
- 缺少官方锚点时，搜索证据不能把候选提升到优先名单。
- 推荐变化必须保留 `推荐理由`、关键词和来源 URL。
- 发信前仍需要人工阅读主页、近作和招生信息。

## 私有资料放置

建议把具体搜索审计写到：

```text
docs/private/web-search-review.local.md
```

人工证据 JSON 写到：

```text
user_private/overrides/web_search_curated.json
```

这两个位置默认不进入 Git。
