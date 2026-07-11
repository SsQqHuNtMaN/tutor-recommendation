# Tutor Recommendation

<p align="center">
  <img src="docs/assets/tutor-recommendation-icon.png" alt="Tutor Recommendation" width="760">
</p>

> 🎓 一个面向导师套磁/研究生申请的本地工作区：把简历、目标学院教师页和公开网页证据整理成可复核的推荐结果，再用网页看板跟进联系状态。

Tutor Recommendation 不是一个“点一下就替你决定导师”的黑箱工具。更推荐的使用方式是：你把项目下载到本地，放入自己的简历和目标学院链接，然后让 Coding Agent 根据仓库里的 README、AGENTS 和 docs 流程完成信息搜集、脚本适配、证据整理与结果生成。最后你在本地网页看板里筛选、统计和维护套磁进度。

## ✨ 适合做什么

- 🔎 整理目标学院教师主页、研究方向、邮箱和个人主页
- 📎 读取部分目标页面上的 PDF 导师库或团队介绍附件
- 📚 补充 DBLP、arXiv、个人主页和网页证据
- 🧭 根据你的学生画像和关键词生成推荐优先级
- 🧹 批量处理同校重叠学院名单时，按个人主页/教师页身份线索去重
- 📝 保留推荐理由和证据来源，方便人工复核
- ✅ 用本地网页看板维护套磁状态、时间、回复和备注
- 🔒 简历、画像、生成结果和联系状态默认只留在本机

## 🧩 使用流程

![Tutor Recommendation 使用流程](docs/assets/tutor-recommendation-workflow.png)

## 🚀 快速开始

### 1. 下载项目

```powershell
git clone https://github.com/SsQqHuNtMaN/tutor-recommendation.git
cd tutor-recommendation
```

### 2. 安装环境

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` 包含 `PyMuPDF`，用于需要从 PDF 简历、导师库或团队介绍附件中抽取文本的目标。

### 3. 放入自己的材料

把简历、申请材料等私人文件放到：

```text
data/private/
```

复制一份学生画像模板：

```powershell
Copy-Item data/templates/student_profile.example.json data/private/student_profile.json
```

你可以自己填写，也可以让 Coding Agent 根据你的简历帮你整理。这个文件会决定匹配时更看重哪些研究方向和关键词。

正式运行缺少或无法解析私有画像时会直接失败，不会静默回退到公开模板。临时演示必须显式使用 `--demo-profile`；使用其他画像文件可传 `--profile <path>`。

### 4. 交给 Coding Agent 执行

在 Codex、Claude Code 或其他 Coding Agent 中，可以直接给它类似这样的任务：

```text
请阅读 README.md、AGENTS.md 和 docs/runbook.md。
我的简历和画像放在 data/private/。
目标学院教师列表链接是：<粘贴目标学院教师页 URL>。
请按照项目流程完成教师信息搜集、证据补全、推荐匹配，并生成本地看板可读取的结果。
```

Agent 通常会做这些事：

- 读取你的学生画像和目标学院页面
- 必要时补充或调整目标采集逻辑
- 运行教师目录、DBLP、arXiv、网页证据等流程
- 生成本地结果文件到 `outputs/`
- 帮你检查强推荐、低置信证据和需要人工复核的行

你也可以参考 [运行手册](docs/runbook.md) 手动执行这些步骤。

三阶段命令为：

```powershell
python build_teacher_match.py <target>
python update_teacher_match_with_dblp.py <target>
python complete_teacher_research.py <target>
```

所有阶段共用同一套排名规则。候选进入优先名单前，官方名录、教师主页或官方 PDF 必须出现画像中的显式核心方向；DBLP、arXiv、已知网页和自动 WebSearch 只能补强或发现证据，不能在没有官方锚点时单独抬高等级。

## 🖥️ 打开网页看板

生成结果后，启动本地看板：

```powershell
.\start_viewer.bat
```

然后访问：

```text
http://127.0.0.1:8765/
```

看板会读取 `outputs/` 中的结果，支持筛选推荐等级、隐藏所有已标记套磁情况的教师、维护套磁状态、记录时间、回复和回复情况备注。“全部教师”视图用于筛选和决策，“已套磁”视图只显示 `套磁情况=已套磁` 的教师；“隐藏已标记”则会隐藏任意非空套磁状态，两者语义不同。主表把推荐等级、匹配分、核心匹配词和锚点/风险放在同一视图；教师详情先展示是否适合进入套磁名单，再按官方方向、论文信号和网页补充分组呈现证据。看板只展示工作簿中的统一排名结论，不会在浏览器中重新计算等级。

服务只允许监听本机回环地址，写操作需要当前进程生成的会话令牌并校验同源请求。不要把它作为无认证的局域网服务暴露。

如果需要把网页里维护的状态同步回 Excel：

```powershell
python sync_contact_status_to_workbooks.py
```

## 📦 你会得到什么

每个目标学院会在本地生成一组结果文件，通常包括：

- 初步教师名录
- DBLP 增强结果
- 综合推荐工作簿
- arXiv / 网页 / 可选 WebSearch 证据明细
- 本地网页看板读取的套磁状态

最终工作簿常见 sheet：

- `优先套磁名单`
- `全量教师名录`
- `DBLP近三年明细`
- `arXiv近三年明细`
- `网页证据明细`
- `匹配依据`

每次新阶段运行还会在学院输出目录写入 `run_manifest.json`，记录画像哈希、评分规则/schema 版本、代码版本、动态年份窗口和输入哈希。可用以下命令检查旧 checkpoint 是否还能用于离线汇总，并对现有结果做不改写 Excel 的影子质量审计：

```powershell
python checkpoint_doctor.py <target>
python result_quality_audit.py --fail-on-violations
```

## 🔐 隐私说明

默认不会入库的内容包括：

- `data/private/` 下的简历、申请材料和学生画像
- `outputs/` 下的生成结果
- `docs/private/` 下的本地交接记录
- PDF、DOCX、XLSX、cache、checkpoint 和联系状态文件

公开仓库只保留通用模板、脚本和方法文档。不要把自己的真实简历、目标结果、教师级复核结论或联系状态提交到 GitHub。

## 📖 更多文档

- [运行手册](docs/runbook.md)
- [工作流方法论](docs/teacher-matching-workflow.md)
- [输出目录规则](docs/output-organization.md)
- [公开交接模板](docs/handoff.md)
