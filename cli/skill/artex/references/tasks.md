# 任务与执行

创建/控制任务、查看进展、维护目标和约束、干预 Worker、管理分类/模板/归档时读本文件。任务聊天见 [会话与交互](conversations.md)，结果交付见 [漏洞、证据与文件](findings.md)。

## 创建与生命周期

`tasks create` 立即触发目标分解和调度。创建前将用户给定的目标、范围、禁止操作和预算写入 request.json；description/goal 描述具体边界，结构化拦截规则放在 `intercept_rules`，不要在任务启动后再补关键限制。

额外字段有 `timeout_seconds`、`llm_profile_ids`、`company_ids`、`source_task_ids`、`coverage_enabled`、`seed_first_intent`。模型链是有序 ID 数组；企业与来源任务 ID 的具体类型沿用 API schema。

```bash
artexctl tasks create --data @request.json
artexctl tasks get 123
artexctl stats --task 123
artexctl tasks pause 123
artexctl tasks resume 123
artexctl tasks wait 123 --wait-timeout 600
artexctl tasks llm-resolution 123
artexctl tasks llm 123 --llm-profile-id 2 --llm-profile-id 3
```

pause 停止 planner/worker；暂停中的任务主 Agent 仍可接收对话指令。resume 适用于暂停任务。终态任务要追加目标或从漏洞深入时使用对应接口，不把 resume 当作通用重跑。

任务终态为 `done` / `failed`。`tasks wait` 在 paused/queued 状态继续等待；退出码 5 表示任务失败，6 表示等待超时。

## 执行过程与 Worker 干预

```bash
artexctl tasks activity --task 123 -q session=main --limit 100
artexctl tasks events --task 123 --duration 30 -q since=0
artexctl intents list --task 123
artexctl intents message 123 456 --message '用户授权的执行约束'
artexctl intents pause 123 456
artexctl intents resume 123 456
artexctl intents rerun 123 456
artexctl tasks rerun-blocked 123
```

history 的 session 可以是 `main`、`plan` 或 `intent:ID`。需要衔接历史与实时事件时，从 history 返回的 `snapshot_cursor` 开始续读 SSE，避免漏掉中间事件。图谱与覆盖图返回 JSON 数据：`exploration graph --task ID`、`tasks coverage ID`、`tasks coverage-graph ID`。

Worker message 自动生成 request_id；需要识别同一次提交时可显式传 `--request-id`。重跑会重新执行工作。`intents cancel` 要附 `--reason`，soft/hard 删除模式通过 JSON 指定；先核对对象与用户要求的删除范围。

## 范围、目标、约束与整理

```bash
artexctl tasks scope 123
artexctl tasks goals 123
artexctl tasks constraints 123
artexctl tasks add-scope 123 --kind root_domain --value example.test --reason '用户授权范围'
artexctl tasks add-goals 123 --text '用户指定的新增目标'
artexctl tasks add-constraints 123 --kind deny --text '用户指定的禁止操作'
artexctl categories list
artexctl templates list
artexctl tasks archive 123
artexctl archives list
```

目标新增/修改可能重新唤起任务；约束修改在后续规划中生效。编辑/删除范围项、目标、约束时使用对应子项 ID。

批量控制、归档用 `tasks control-batch/archive-batch --set 'task_ids=["123","124"]'`，控制还需 `--set action=pause` 或 resume。归档恢复用 `archives restore ARCHIVE_ID`；归档 ID 与 task ID 分开使用。分类批量调整、归档批量恢复/删除等通过 `api list` 查找，按实际请求填入 JSON。
