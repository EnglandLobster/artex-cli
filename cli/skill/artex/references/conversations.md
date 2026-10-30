# 会话与交互

向任务主 Agent 发指令、管理独立 Agent 会话、附加文件或使用旁路问答时读本文件。Worker 干预见 [任务与执行](tasks.md)。

## 任务主 Agent

```bash
artexctl tasks sessions --task 123
artexctl tasks chat --task 123 --message '用户授权的任务指令' --timeout 600
artexctl tasks stop-chat 123
artexctl tasks new-session --task 123
```

始终显式传 task ID。任务主对话和 planner/worker 暂停状态独立；不要把向暂停任务发消息视为纯只读操作。new-session 新建主会话分段，原任务资产、目标和图谱仍保留；指定历史分段可在聊天 JSON 中传 `seg`。

## 独立 Agent 会话

先从 `agents list` 获取实际 agent key，再创建会话，不假定一定存在名为 chat 的 Agent。

```bash
artexctl conversations list
artexctl conversations create --agent-key AGENT_KEY --title '授权项目讨论'
artexctl conversations send 456 --message '用户授权的操作指令' --timeout 600
artexctl conversations messages 456 --limit 100
artexctl conversations messages 456 -q since=CURSOR
artexctl conversations stop 456
```

conversation ID 独立于 task ID。send 是异步提交；继续读取 messages 的 `items`、`running` 和 cursor，直到本轮完成或需要处理阻塞。初次读取无 since 是最新历史页，向前翻页用 `-q before=ID`；增量跟进用 since。

改标题/配置绑定使用 `conversations update/profile`，批量删除与单条消息详情可从 `api list conversation` 发现。

## 附件

```bash
artexctl api call chat-upload -q scope=task -q id=123 --form file=@notes.txt
# 独立会话改为 scope=session、id=对应 conversation ID
```

上传返回 attachments 数组；将它与 message 一起放入后续聊天 JSON：任务用 `tasks chat --task ID --data @message.json`，独立会话用 `conversations send ID --data @message.json`。使用返回的路径，不自行拼接服务器绝对路径。

## 旁路问答

用 `api list side-questions` 找到 task 主会话、worker 或 conversation 的接口，再 `api describe OPERATION`。POST 请求包含 `question` 和 `client_request_id`（建议 UUID）；同一请求重试保留相同 ID 和问题。需要已有主 Agent 上下文快照，否则服务返回 409。

GET 读取历史、current、snapshot；POST 提交后按返回的请求 ID 读取 `side-events`，停止用 `cancel-side-request`。DELETE 清理该父会话的旁路历史。不要混用父会话 ID 和 side request ID，也不要把清理历史当成普通读取。
