# ARTEX CLI + Agent Skill

`artexctl` 是现有 Go 服务的独立客户端。Python 3.10+ 即可运行，无 pip 依赖；通过 HTTP API 复用 UI 的业务逻辑、鉴权、审批和留痕。后端仍由原有 `artex` 启动。

## 安装与接入

```bash
# 源码直接使用
python3 bin/artexctl --help

# 本机安装：~/.local/bin/artexctl + ~/.agents/skills/artex
python3 cli/install.py

# 远端安装：/opt/artex-cli/artexctl + /usr/local/bin/artexctl + 远端 skill
python3 cli/install.py --ssh myvps

# 本机通过 SSH 连接远端已有后端
artexctl profile set myvps --ssh myvps --url http://127.0.0.1:8787
artexctl --profile myvps auth login
artexctl profile use myvps
artexctl tasks list
```

`~/.local/bin` 需在 PATH 中，也可用其绝对路径。独立产物由 `python3 cli/build.py` 生成到 `dist/artexctl`，拷贝到其他 Python 3.10+ 主机即可执行。安装器只修改独立客户端目录、命令链接和此 skill，遇到同名但非安装器管理的文件会停止，不覆盖后端。

远端本机也能直接 `ssh myvps artexctl tasks list`；本机和远端配置各自独立。HTTP/SSE/文件传输都可走 SSH 隧道，无需新增公网端口。SSH 模式的 URL 指远端 HTTP listener；直连可用 HTTPS URL。

仅在新部署时用 `auth init` 初始化密码；已有部署用 `auth login`。非交互密码经 stdin 输入，不放命令行：`artexctl auth login --password-stdin`。已有服务器文件管理权限的操作者也可显式执行：

```bash
artexctl --profile myvps auth key-login --key-file /opt/artex/jwt.key
# 远端本机
ssh myvps artexctl auth key-login --key-file /opt/artex/jwt.key
```

这是服务器管理员登录方式：在密钥所在机器签发与当前后端一致的 HS256 token，只传回有期限的 token，签名密钥留在原处。默认有效一天，`--ttl` 可设 60–604800 秒。随后先验证受保护接口，再以 0600 权限保存 token 和登录方式（密钥路径、有效期），不保存密码或签名密钥。

`key-login` 默认启用自动续期：后续 CLI 请求会在 token 到期前续期（提前有效期的 10%，最多 5 分钟），已过期或缺少 token 时也会自动恢复。改密码导致密钥轮换时，CLI 在收到后端鉴权拦截的 `401` 后续期并重试一次；并发调用共用续期结果。续期用当前 profile 的原登录方式，在本机或 SSH 远端签发并验证新 token。SSH 或密钥读取失败会直接报错。使用 `--no-auto-renew` 可选择只保存本次 token；密码登录、退出登录或更改 profile 连接地址会清除原自动续期设置。显式提供 `ARTEX_TOKEN` 或 Authorization 请求头时沿用调用者的凭据。

配置路径：`$ARTEX_CLI_CONFIG`，默认 `$XDG_CONFIG_HOME/artex/config.json`（通常为 `~/.config/artex/config.json`）。连接优先级：命令行 > `ARTEX_URL` / `ARTEX_SSH` > profile。凭据使用 `ARTEX_TOKEN` 或 profile token；更换连接地址时不沿用旧凭据。`ARTEX_PROFILE` 或 `--profile` 选择 profile，`profile use` 设置默认。`profile list` 隐去 token；`auth logout` 清除该 profile 本地保存的 token。

## 常用操作

```bash
artexctl health
artexctl stats
artexctl tasks create --data @authorized-task.json  # 立即触发调度
artexctl tasks get 123
artexctl tasks pause 123
artexctl tasks resume 123
artexctl tasks chat --task 123 --message '用户授权的任务指令' --timeout 600
artexctl intents message 123 456 --message '用户授权的执行约束'
artexctl tasks events --task 123 --duration 30 -q since=0
artexctl tasks wait 123 --wait-timeout 600
artexctl findings list --task 123 --severity high
artexctl findings retest 789 --notes '修复版本与复测条件'
artexctl findings export --task 123 --export-format md-zip -o evidence.zip
artexctl tasks report --task 123 -o report.md
artexctl approvals pending
artexctl approvals get 42
artexctl approvals deny 42
artexctl workspace upload -q path=tasks/123 -F file=@notes.txt
artexctl workspace download -q path=tasks/123/report.md -o report.md
```

授权任务 JSON 示例（目标与限制由操作者填写）：

```json
{
  "name": "授权项目",
  "description": "用户授权的目标、资产范围和禁止操作",
  "goal": "具体测试目标与停止条件",
  "timeout_seconds": 600,
  "llm_profile_ids": [2],
  "seed_first_intent": false,
  "intercept_rules": []
}
```

`tasks create`、`findings deepen/retest`、发送 Agent 消息等会实际运行 Agent；CLI 功能验证使用本地 fixture，不会向真实目标发起扫描。

全部功能映射见 [CAPABILITIES.md](CAPABILITIES.md)，Agent 工作方式见 [SKILL.md](skill/artex/SKILL.md)。

## 完整接口、输入与输出

```bash
artexctl api list findings
artexctl api describe get-finding
artexctl api call get-finding --path id=789
artexctl api request GET /api/tasks
artexctl tasks create --description '测试描述' --goal '测试目标' --dry-run
artexctl tasks control-batch --set 'task_ids=["123","124"]' --set action=pause
artexctl skills write demo references/notes.md --content-file notes.md
```

默认 stdout 为单个 JSON 值，`--format pretty` 美化，`--format raw` 原样输出。报告默认输出 Markdown；二进制下载用 `--output PATH`（临时文件写完再替换）或 `--output -`。错误是 stderr 上的 JSON，普通响应不混入进度日志。

筛选用 `-q KEY=VALUE`（可重复，覆盖快捷筛选），复杂 JSON 用 `-d @file.json` / `-d -`；顶层字段用 `-s KEY=VALUE`，合法 JSON 值解析为数字、数组、布尔值或 null，其余保留字符串。强制字符串数字用 `--set 'value="123"'` 或 JSON 文件。`--content-file` 将 UTF-8 文件置入 JSON `content`。`-F file=@PATH` 支持重复文件字段，磁盘暂存 multipart，避免大文件全部驻留内存；`--body-file` 用于原始 body 接口。

SSE 自动转为 NDJSON，保留 `event` / `id` / `data`，支持 `--max-events` 和 `--duration`，Ctrl-C 或结束后清理 SSH 隧道。断线不自动重连；活动流用最后事件 id 的 `-q since=ID` 或 `-H Last-Event-ID=ID` 续读。`--timeout` 是 socket 等待超时，默认 60 秒，耗时聊天可调大；`tasks wait --wait-timeout` 是任务轮询总时限。

仅对后端在业务执行前明确拦截的鉴权失败自动续期并重试一次；超时、传输失败和其他 HTTP 错误不自动重试。写操作超时应先查询提交结果，避免创建重复任务或消息。会话发消息通常异步返回，后续读 messages 的 `running`/cursor；`tasks wait` 只监控任务状态，`paused`/queued 仍保持等待。

退出码：0 成功；1 传输/本地 IO 失败；2 参数或输入失败；3 鉴权失败；4 HTTP API 错误；5 任务终态 failed；6 等待超时；130 用户中断。参数解析错误由 argparse 输出到 stderr。

## 验证与维护

```bash
python3 -m unittest discover -s cli/tests -v
python3 cli/generate_catalog.py --check
python3 cli/build.py
dist/artexctl --version
```

接口清单来自当前源码的路由注册，含两组动态路由（旁路问答、漏洞流量证据）。后端增加接口后运行 `python3 cli/generate_catalog.py` 并检查清单差异；新的动态注册方式需更新生成器。测试确保常用命令实际指向已注册接口，覆盖真实 HTTP 客户端、登录、二进制与多文件传输、SSE、失败退出码等。

`api describe` 的字段提示来自 handler 局部代码，辅助查找，不是完整请求 schema；named request types、公共查询解析器和嵌套对象应结合原源码判断。远端版本有额外接口时可先 `api request` 调用，再更新目录。
