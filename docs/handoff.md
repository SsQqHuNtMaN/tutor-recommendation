# 公开交接模板

本文件只保留可公开的交接格式。真实申请者画像、当前爬取结果、教师级证据、联系状态和阶段进展请写入本地忽略目录，例如：

```text
docs/private/handoff.local.md
docs/private/project-context.local.md
```

## 交接时建议记录什么

面向协作者或未来自己的公开交接可以记录：

- 本次改动影响了哪些模块。
- 新增或变更了哪些命令入口。
- 输出 schema 是否变化。
- ranking policy/schema 版本是否变化，是否需要重跑旧工作簿。
- `run_manifest.json` 和 checkpoint fingerprint 是否与当前输入一致。
- 联系状态字段或允许值是否变化。
- 需要重新运行哪些测试或脚本。
- 哪些行为是通用规则，应该同步到 README、runbook 或 workflow。

不要记录：

- 真实简历、申请表、学生背景和目标方向。
- 已生成 Excel 的学校/学院数量、候选人数和推荐结论。
- 具体教师的论文、主页、人工判断或联系状态。
- `outputs/`、cache、checkpoint、`contact_status.json` 的内容。

## 可复制模板

```md
# 本地阶段交接

更新时间：YYYY-MM-DD

## 已完成

- ...

## 代码变化

- ...

## 文档变化

- ...

## 需要复核

- ...

## 验证

- tests: ...
- checkpoint doctor: ...
- result quality audit: ...

## 下一步

1. ...
2. ...
3. ...

## 私有状态位置

- 私人材料：user_private/source/
- 学生画像：user_private/profile/student_profile.json
- 输出结果：outputs/<school_slug>/<college_slug>/
- 联系状态：outputs/contact_status.json
```

## 当前公开状态

项目的公开使用入口见：

- [README](../README.md)
- [Coding Agent 工作流](agent-workflow.md)
- [运行手册](runbook.md)
- [工作流方法论](teacher-matching-workflow.md)
- [输出目录规则](output-organization.md)
- [Viewer 日历与教师列表整合布局](viewer-integrated-layout.md)
- [WebSearch 补充层说明](web-search-supplement.md)
