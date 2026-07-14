# 用户私人资料区

这是项目中唯一面向用户的私人材料入口。除本说明和公开请求模板外，目录里的内容都会被 Git 忽略。

单画像兼容结构由 Coding Agent 或 `tutor setup` 自动创建：

```text
user_private/
  source/                    # 简历、申请表、成绩单、个人说明
  profile/
    student_profile.draft.json
    student_profile.json    # 用户确认后的正式画像
  overrides/                 # 人工确认的消歧和证据覆盖
  request.md                 # 本次目标院校、学院和偏好
```

需要为不同学生或不同申请方向保留独立结果时，Agent 会建立命名画像：

```text
user_private/
  profiles/
    <profile_id>/
      source/
      student_profile.draft.json
      student_profile.json
  active_profile.json
  overrides/
```

用户通常只需要：

1. 把材料放入 `source/`，或告诉 Agent 要新建一个独立画像。
2. 复制 `request.example.md` 为 `request.md` 并填写目标，或直接在对话中告诉 Coding Agent。
3. 要求 Coding Agent 读取材料、生成画像草稿、集中询问待确认项并完成匹配。

画像草稿不能直接驱动正式匹配。Coding Agent 必须让用户确认研究方向、关键词权重和强信号词，再保存到所选画像目录并通过校验。不同画像的材料、结果、checkpoint 和联系状态不会混用。

兼容期内，旧 `data/private/student_profile.json` 仍可读取，但新任务优先使用这里。
