# artex-cli

ARTEX 平台的管理 CLI（`artexctl`）与配套 Agent Skill。

[ARTEX](https://github.com/EnglandLobster/ARTEX-latest) 是一个自主漏洞挖掘 Agent 平台（Go 后端 + Web UI）。本仓库提供与后端 HTTP API 交互的独立客户端：

- **零依赖**：Python 3.10+ 标准库实现，无 pip 依赖；构建产物是单文件 zipapp，拷贝到任何 Python 3.10+ 主机即可执行
- **SSH 隧道传输**：`--ssh` 自动建立/清理本地转发，无需为后端开放公网端口，HTTP_PROXY 不影响隧道流量
- **完整 API 目录**：内置 266 个后端接口的路由清单（`api list` / `api describe` / `api call`），新接口可用 `api request` 直接调用
- **凭据安全**：token 以 0600 权限保存；key-login 在密钥所在机器签发、签名密钥不离开服务器；自动续期仅对后端明确拦截的 401 重试一次
- **流式与文件**：SSE 自动转 NDJSON（支持 `--max-events` / `--duration` / 断线续读），multipart 磁盘暂存支持大文件上传
- **Agent Skill**：`cli/skill/artex` 是给外部 Agent（Claude Code、ZCode 等）的操作手册，安装后 Agent 即可按文档驱动本 CLI

## 快速开始

```bash
git clone https://github.com/EnglandLobster/artex-cli.git
cd artex-cli

# 源码直接使用
python3 bin/artexctl --help

# 本机安装：~/.local/bin/artexctl + ~/.agents/skills/artex
python3 cli/install.py

# 安装到远端服务器（任意 SSH 别名）：/opt/artex-cli + /usr/local/bin + 远端 skill
python3 cli/install.py --ssh myvps

# 连接远端已有后端
artexctl profile set myvps --ssh myvps --url http://127.0.0.1:8787
artexctl --profile myvps auth login
artexctl profile use myvps
artexctl tasks list
```

后端由 [ARTEX 主仓库](https://github.com/EnglandLobster/ARTEX-latest)启动，本客户端不部署、不修改后端。

## Agent Skill

`python3 cli/install.py` 会同时把 [cli/skill/artex](cli/skill/artex/SKILL.md) 安装到 `~/.agents/skills/artex`（远端安装则对应远端目录）。Skill 采用按需加载：入口 [SKILL.md](cli/skill/artex/SKILL.md) 按当前任务只引用对应的专题文档（任务、会话、漏洞、资产、审批、平台管理）。

## 文档

- [cli/README.md](cli/README.md) — 安装、认证、常用操作、完整接口用法与退出码
- [cli/CAPABILITIES.md](cli/CAPABILITIES.md) — CLI 命令到平台能力的完整映射
- [cli/acceptance.json](cli/acceptance.json) — 真实后端的验收记录（命令、退出码与返回结构）

## 开发

```bash
python3 -m unittest discover -s cli/tests -v   # 测试套件（本地 HTTP fixture，不连真实后端）
python3 cli/build.py                            # 构建 dist/artexctl
dist/artexctl --version
```

`cli/generate_catalog.py` 从后端源码的路由注册重新生成 API 目录（`cli/artex_cli/catalog.json`）。它需要 [ARTEX 后端源码树](https://github.com/EnglandLobster/ARTEX-latest)，独立检出时用 `--root` 指向后端仓库：

```bash
git clone https://github.com/EnglandLobster/ARTEX-latest.git ../ARTEX-latest
python3 cli/generate_catalog.py --root ../ARTEX-latest          # 重新生成
python3 cli/generate_catalog.py --root ../ARTEX-latest --check  # 校验是否过期
```

后端新增接口时可先用 `api request` 直接调用，再重新生成目录。

## 授权使用的提醒

本工具面向已获授权的安全测试与自有平台运维。创建任务、复测、深入等操作会实际驱动 Agent 执行工作，测试目标与范围由操作者自行授权并负责。

## License

[AGPL-3.0](LICENSE)，与 ARTEX 主项目一致。
