# Changelog

## 0.1.1 - 2026-10-30

- 修复 `findings list` 筛选失效：带 `--task` / `--severity` / `--status` / `-q` 筛选而未指定分页时自动补 `limit`，确保命中后端的筛选分页分支；此前这类请求会静默退化为未筛选的全量汇总列表。
- 独立仓库支持：`generate_catalog.py` 缺少后端源码树时给出明确提示，`install.py` 与测试在独立检出下相应跳过 catalog 校验。

## 0.1.0 - 2026-10-20

- 首个公开版本：`artexctl` CLI、Agent Skill、测试套件与安装器。
