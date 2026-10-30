---
name: artex
description: 通过 artexctl CLI 操作 ARTEX 漏洞挖掘 Agent 平台，支持 SSH 远程任务、会话、资产、发现与复测、审批、证据和平台配置。用户提到 ARTEX、查询其任务/漏洞，或要求调用该平台时使用；实际测试的目标与范围沿用用户授权。
---

# ARTEX

通过 `artexctl` 操作 ARTEX 的任务、会话、资产、漏洞、审批和平台配置。本 skill 指导外部 Agent 调用平台；平台内部供扫描 Agent 使用的 skills 由 `artexctl skills` 管理。

## 入口与按需加载

先用 `artexctl profile list` 确认连接，再用 `artexctl health` 检查服务。沿用已有 profile；连接、认证或通用参数不清楚时读连接文档。

根据当前请求只读取对应专题；跨功能任务再读取所需的相邻专题，不预先加载全部文件。

| 当前要做的事 | 读取文档 |
| --- | --- |
| 连接远程服务器、登录、处理认证/传输错误、查询 CLI 参数或其他 API | [连接与 CLI 约定](references/connection.md) |
| 创建/控制任务、查看执行与覆盖度、维护目标/约束、干预 Worker、归档 | [任务与执行](references/tasks.md) |
| 任务主 Agent 对话、独立会话、附件、旁路问答 | [会话与交互](references/conversations.md) |
| 查看/处置漏洞、复测/深入、流量证据、报告导出、工作空间文件 | [漏洞、证据与文件](references/findings.md) |
| 查询/导入资产、关联企业和任务、FOFA / ScopeSentry 同步 | [资产与同步](references/assets.md) |
| 处理待审批操作、查看裁决历史、维护全局/任务规则和审批裁判 | [审批与规则](references/approvals.md) |
| 配置 LLM / Agent / 工具 / MCP / 内部 skills，查看日志、通知或更新 | [平台管理](references/administration.md) |

## 共用约定

- 沿用用户授权的目标、范围与操作限制。创建任务、发送 Agent 指令、复测和深入会实际执行工作；仅查询或验证连接时不启动扫描。
- 明确使用 task ID、conversation ID 和 finding_id；任务查询与对话显式传 `--task ID`，避免全局 active task 改变操作对象。
- 具体参数以 `<资源> <操作> --help`、`api list KEYWORD` 和 `api describe OPERATION` 为入口；复杂请求按需核对文档或源码中的 schema。
- HTTP 写请求超时后先查询提交结果，再决定重试，避免重复创建任务或消息。
