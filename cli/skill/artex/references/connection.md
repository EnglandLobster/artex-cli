# 连接、认证与 CLI 约定

连接配置、认证失败、输入输出、通用 API 或传输问题时读本文件。

## 本机与远程服务器

已有 `myvps` profile 时使用 `artexctl --profile myvps health`。首次配置：

```bash
artexctl profile set myvps --ssh myvps --url http://127.0.0.1:8787
artexctl --profile myvps auth login
artexctl profile use myvps
```

`--ssh` 下 URL 指远端 HTTP listener；SSH 模式自动创建并清理临时本地转发，HTTP 请求不受调用端 HTTP_PROXY 影响。直连服务可使用 HTTPS URL。

找不到命令时尝试 `~/.local/bin/artexctl`。也可直接在远端执行 `ssh myvps artexctl health`，它使用远端自己的 profile 和凭据。

## 认证

`auth status` 检查管理员密码是否初始化；新部署用 `auth init`，已有部署用 `auth login`。密码从交互提示或 `--password-stdin` 输入，不放命令行参数。

已拥有服务器管理权限并选择以其密钥登录时：

```bash
artexctl --profile myvps auth key-login --key-file /opt/artex/jwt.key
# 在远端本机登录
ssh myvps artexctl auth key-login --key-file /opt/artex/jwt.key
```

`key-login` 成功后默认保存登录方式（密钥路径与 TTL），由 CLI 自动续期。token 默认一天有效；每次受保护请求前检查，到期前有效期的 10%（最多 5 分钟）、已过期或 token 缺失时续期。后端因密钥轮换等原因在业务执行前返回鉴权 `401` 时，续期后重试一次；并发命令共用续期结果。旧版 CLI 保存的 profile 需用新版执行一次 `key-login` 以记录续期方式。

key-login 在密钥所在机器签发 token，签名密钥留在服务器。不要读取或显示签名密钥、配置中的 token。CLI 在保存新 token 前验证受保护接口；续期失败时报告具体的连接或认证错误。`--no-auto-renew` 仅保存本次 token；密码登录、退出登录或更换 profile 的连接地址会清除续期方式。显式设置 `ARTEX_TOKEN` 或 Authorization 请求头时使用调用者的凭据。

配置默认在 `~/.config/artex/config.json`，可由 `ARTEX_CLI_CONFIG` 覆盖；`--profile` / `ARTEX_PROFILE` 选择 profile。连接优先级为命令行、环境变量 `ARTEX_URL` / `ARTEX_SSH`、profile。凭据使用 `ARTEX_TOKEN` 或 profile token。用 `profile list` 查看脱敏状态，`auth logout` 清除当前 profile 保存的 token 和自动续期方式。

## 参数与接口发现

- 筛选：`--query KEY=VALUE`（简写 `-q`，可重复）。它覆盖对应的快捷筛选值。
- JSON 请求：`--data @request.json` 或 `--data -` 从 stdin 读取；顶层字段可用 `--set KEY=VALUE`（简写 `-s`）。合法 JSON 值保留数字、数组、布尔类型；数字字符串用 `--set 'value="123"'`。
- 文件：下载/导出用 `--output PATH`，上传用 `--form file=@PATH`，可重复上传文件字段；`--content-file PATH` 读取 UTF-8 文件写入 JSON `content`。
- 请求预览：`--dry-run` 不连接或写入服务。不要把含凭据的请求预览输出到共享日志。
- 其他能力：`api list KEYWORD` → `api describe OPERATION` → `api call OPERATION --path id=123`。字段提示来自 handler，复杂嵌套对象仍需核对 schema；远端新增接口可用 `api request METHOD /api/path`。

## 输出与恢复

stdout 默认 JSON，`--format pretty` 美化；报告可直接输出 Markdown，二进制用 `--output PATH` 或 `--output -`。错误在 stderr；常规错误为 JSON，参数解析错误由 argparse 输出。

SSE 自动输出 NDJSON，保留 event/id/data。用 `--duration SECONDS` 或 `--max-events N` 有界读取。活动流断线后可用最后事件 id 的 `-q since=ID` 或 `-H Last-Event-ID=ID` 续读。除业务执行前的鉴权拦截可自动续期重试一次外，HTTP 请求不自动重试，SSE 不自动重连；写操作超时先查询提交结果，读取失败可重试。

`--timeout` 是 socket 等待超时，默认 60 秒，耗时对话可设 600。退出码：0 成功，1 传输/IO 失败，2 输入失败，3 鉴权失败，4 HTTP API 错误，5 任务终态 failed，6 任务等待超时，130 用户中断。404 时核对 `health` 版本和具体接口，不将错误替换为空结果。
