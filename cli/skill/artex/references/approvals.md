# 审批与规则

处理待审批操作、查看裁决/执行记录、维护全局或任务规则、配置审批裁判时读本文件。

## 单次审批

```bash
artexctl approvals pending
artexctl approvals get 42
artexctl approvals allow 42
artexctl approvals deny 42
artexctl approvals history --page 1 --size 20
artexctl approvals detail 42
artexctl approvals execution 42
```

决定前读取实际操作、目标、上下文和预期效果，再按用户授权选择 allow/deny；不批量自动放行未知操作。pending ID 与 history ID 按各自返回值使用。

审批已被处理时服务可能返回 409，重新读取当前状态，不重复强行提交。裁决和实际执行结果分别读取：allow 只表示允许执行，后续结果从 execution/任务活动核对。

## 规则与裁判

```bash
artexctl rules list
artexctl asset-rules list
artexctl tasks intercept-rules 123
artexctl api list intercept
```

`rules` 是全局操作拦截规则，`asset-rules` 是全局资产允许/拦截规则，task intercept-rules 只针对某个任务。先确定用户要改的作用域，再使用对应 create/update/delete 或 toggle 接口。复杂匹配条件用 JSON，不用全局规则替代单次审批。

工具审批范围、裁判 LLM 配置及其用量从 `api list intercept` 找到具体操作，再用 `api describe` 确认 method/path 和字段。调整规则或裁判会影响后续审批；检查生效结果时优先读回配置与现有记录，不额外运行目标测试。
