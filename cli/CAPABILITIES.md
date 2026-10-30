# UI → CLI 能力映射

CLI 接入 UI 使用的同一批后端接口。当前源码共 266 条 API，全部收录于 `artexctl api list`；常见流程另提供下列资源命令。`api call` 根据 operation 名调用，`api request METHOD /api/path` 可直接调用远端扩展。

| UI 能力 | 常用命令 | 其他接口与语义 |
| --- | --- | --- |
| 仪表盘、健康、统计 | `health`、`stats --task ID`、`tokens usage/daily/conversations` | token 的按模型/会话明细可从 api 目录查找 |
| 任务列表与生命周期 | `tasks list/create/get/update/delete/pause/resume/wait` | 创建立即调度；批量控制与归档有独立命令；删除选项沿用 API JSON |
| 任务分类、模板、归档 | `categories`、`templates`、`archives` | 分类批量调整、归档批量恢复/删除通过 api 目录 |
| 测试范围、目标与约束 | `tasks scope/add-scope/remove-scope`、`goals/add-goals/update-goals/remove-goals`、`constraints/add-constraints/update-constraints/remove-constraints` | 新增/修改目标可能重新唤起任务 |
| 任务关联资产与模型链 | `tasks asset-refs/add-assets/remove-assets/llm/llm-resolution` | 继承任务、关联企业和超时可在创建 JSON 指定 |
| 执行过程与探索图 | `intents list/pause/resume/cancel/rerun/message`、`tasks activity/events/sessions`、`exploration graph/nodes/frontier` | 返回图结构和事件，不绘制浏览器图形；worker message 自动生成 request_id |
| 人在环路任务对话 | `tasks chat --task ID`、`tasks stop-chat/new-session` | 附件通过 `api call chat-upload`，返回 attachments 再放入消息 JSON |
| 独立 Agent 会话 | `conversations list/create/send/messages/stop/update/profile/delete` | 异步发送后 messages 返回 running/cursor；消息详情和批量删除可用 api |
| 旁路问答 | `api list side-questions` | task、worker、conversation 的 list/create/clear、事件和 cancel 全覆盖 |
| 发现、处置、复测、深入 | `findings list/get/update/delete/stats/groups/asset-tree/lineage/retest/retests/deepen` | 使用 finding_id；复测会运行独立 Agent，deepen 会生成后续任务 |
| 报告与证据导出 | `tasks report`、`findings export --export-format md-single/md-zip/csv/json` | 可选按筛选/全部/指定 IDs；md-zip 带流量证据；复测历史需单独读取 |
| 漏洞流量绑定与排序 | `findings traffic/bind-traffic`，其余从 `api list traffic` 选择 | 详情、body、编辑、解除关联和 order 均可调用 |
| 资产和企业 | `assets list/create/delete/counts`、`companies list/create/get/delete/scope/reattribute` | 复杂资产图查询 DSL 通过 -q 参数传递；资产 DELETE 是集合接口 |
| 流量录制与工具记录 | `traffic list/hosts/get/blob/delete/delete-all`、`commands list/stats`、`llm-records list/get` | 全量清理、模型记录删除具有真实删除效果 |
| 工作空间 | `workspace list/read/write/mkdir/delete/upload/download` | 上传重复 -F file=@PATH；下载原始二进制；路径在服务端工作空间内解释 |
| Agent 配置与提示词 | `agents list/create/get/update/delete/config/prompt/reset-prompt/wrapup/prompts/variables/visibility` | timeout wrapup、预览、可见性写入和触发器可从 api 目录发现 |
| 内置及自定义工具 | `tools list/update/reset`、`custom-tools create/update/delete/test` | test 会实际运行工具，不能仅作连接检查 |
| MCP | `mcp list/create/delete/tools/refresh` | create/save 的完整连接类型、headers 等通过 JSON 传入 |
| ARTEX 内部 skills | `skills list/create/delete/files/read/write/meta/upload/usage/missing` | ZIP 上传、子目录、文件删除及可见性均有 API；与本客户端配套 skill 区分 |
| LLM 配置与故障恢复 | `llm get/set/test/models/profiles/save-profile/delete-profile/activate/pool/reset-pool/retry-policy/set-retry-policy` | key 经文件/stdin JSON 传入；test/models 会访问配置的提供商 |
| 审批与操作规则 | `approvals pending/get/allow/deny/history/detail/execution`、`rules`、`asset-rules` | 任务规则、全局裁判、工具审批配置和用量均可从 api 目录操作 |
| FOFA / ScopeSentry | `sync fofa-config/fofa-set/fofa-quota/fofa-preview/fofa-import/status/datasource/projects/tasks/run` | 复用既有数据源；preview/import 可能消耗第三方配额 |
| 系统配置、通知与更新 | `settings get/set`、`notify list/create/update/delete/test/deliveries/retry`、`update check/apply/rollback/stream` | 通知会发送消息；apply/rollback 会重启后端；配置完整 JSON 沿用 UI |
| 后端日志与审计 | `logs list/history/follow`、`audit --task ID` | SSE NDJSON；可按 duration/max-events 有界读取 |
| 登录、改密、远端连接 | `auth status/init/login/change-password/key-login/logout`、`profile list/set/use/delete` | JWT、HTTPS、SSH 临时转发、0600 凭据文件；key-login 默认自动续期，鉴权拦截后最多重试一次；不改后端认证规则 |

CLI 不复刻图谱布局、颜色主题、侧栏偏好和浏览器下载弹窗。这些 UI 行为对应的数据、读写和导出能力在命令中保留。后端未实现的功能（如当前 `gc` 的空实现）仍保持原有行为，CLI 不宣称增加该功能。

接口清单指本仓库源码，不是假定远端版本完全相同。远端 404 时先确认 `health` 版本及具体接口；不要把未知接口的失败改成成功空结果。
