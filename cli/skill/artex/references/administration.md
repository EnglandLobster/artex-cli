# 平台管理

LLM、Agent、工具、MCP、平台内部 skills、系统配置、日志、通知与版本管理时读本文件。连接/认证问题见 [连接与 CLI 约定](connection.md)，操作规则见 [审批与规则](approvals.md)。

## LLM 与 Agent

```bash
artexctl llm profiles
artexctl llm save-profile --data @llm-profile.json
artexctl llm activate --set id=2
artexctl llm pool
artexctl llm retry-policy
artexctl agents list
artexctl agents get AGENT_KEY
```

任务级模型链用 `tasks llm TASK_ID`，与全局 activate 区分。profile 更新留空 API key 保持原 key；凭据经 JSON 文件/stdin 输入。`llm test/models` 会实际访问提供商；pool reset 清除熔断状态，按具体故障使用。

Agent 的 config/prompt/wrapup、提示词版本/变量有对应子命令；先读当前配置再写目标字段。触发器与可见性操作从 `api list trigger` / `api list visibility` 查找。

## 工具、MCP 与内部 skills

```bash
artexctl tools list
artexctl mcp list
artexctl mcp tools 2
artexctl skills list
artexctl skills files example
artexctl skills read example references/notes.md
artexctl skills write example references/notes.md --content-file notes.md
artexctl skills upload --form file=@example.zip
artexctl skills usage example
artexctl skills missing
```

`tools update/reset`、`custom-tools create/update/delete/test` 操作平台工具；test 会实际运行工具。MCP 保存用 `mcp create --data @mcp.json`，连接类型、URL/command/headers 按 schema 填写；刷新用 `mcp refresh ID`。

`artexctl skills` 管理后端扫描 Agent 使用的技能，不会更新本机或远端 Codex 的这个 artex 调用 skill。ZIP 需包含带 name/description frontmatter 的 SKILL.md；覆盖已有技能需显式传 `-q overwrite=true`。技能 meta 可更新 description、license、compatibility 和 mcps，技能子目录/可见性可从 API 目录发现。

## 配置、通知与更新

```bash
artexctl settings get
artexctl settings set --data @settings-patch.json
artexctl notify list
artexctl notify deliveries
artexctl update check
```

settings 使用局部更新 JSON。通知配置使用 notify create/update/delete；test/retry 会发送真实消息，仅在用户授权对应发送操作时执行。`update apply/rollback` 会更换程序并重启后端，需要把正在运行的任务纳入本次操作判断。只查看状态时不执行这些操作。

## 可观测性

```bash
artexctl stats
artexctl tokens usage
artexctl logs history
artexctl logs follow --duration 15
artexctl commands list --task 123 --size 50
artexctl commands stats --task 123
artexctl llm-records list --task 123 --size 50
artexctl audit --task 123
```

token 按模型明细、完整 LLM 记录与流量 blob 等通过 API 目录查询；日志和完整记录可能包含任务数据，按当前问题选择必要范围。图谱、覆盖图与仪表盘通过 JSON 提供数据，CLI 不复刻浏览器的布局、主题和侧栏偏好。
