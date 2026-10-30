# 资产与同步

查询/导入资产、企业资产范围、关联任务资产、FOFA 或 ScopeSentry 同步时读本文件。任务自身的 scope/目标/约束见 [任务与执行](tasks.md)。

## 资产与企业

```bash
artexctl assets counts
artexctl assets list --limit 50 -q offset=0
artexctl assets list -q task_id=123 --limit 50
artexctl companies list
artexctl companies get 42
artexctl tasks asset-refs 123
artexctl tasks add-assets 123 --set 'asset_ids=[101,102]' --set source_summary='用户选择的已有资产'
```

资产接口按任务筛选使用 `task_id`，不是通用 `--task` 的 task 参数。按返回的 total 和 offset 分页；复杂检索用 `-q dsl=EXPRESSION`，语法按平台支持的 DSL 填写。

创建/导入资产用 `assets create --data @assets.json`，企业创建和范围维护用 `companies create/scope --data @request.json`。企业范围重归属用 `companies reattribute`，会更新资产归属。

资产删除是集合接口 `assets delete --set 'ids=[101,102]'`；任务解除资产关联用 `tasks remove-assets TASK_ID ASSET_ID`，选择与用户意图对应的操作。

## FOFA

```bash
artexctl sync fofa-config
artexctl sync fofa-quota
artexctl sync fofa-preview --data @fofa-query.json
artexctl sync fofa-import --data @fofa-import.json
```

沿用既有配置，需修改时用 `sync fofa-set --data @config.json`。preview/import 会查询第三方并可能消耗配额。导入 JSON 的 query、size、create_company、company_name 等字段先通过 `api describe fofa-import` 核对，查询目标限于用户要求的范围。

## ScopeSentry

```bash
artexctl sync status
artexctl sync projects
artexctl sync tasks
artexctl sync run --data @sync-request.json
```

按 project/task 维度从返回列表选择 targets，指定 asset_types、dimension 等字段。连接配置用 `sync datasource --data @datasource.json`，API key 经本地文件或 stdin 传入，不输出到共享日志。同步后的资产和企业归属以 ARTEX 返回结果核对。
