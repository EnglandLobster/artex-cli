# 漏洞、证据与文件

查询/处置漏洞、复测、继续深入、查看流量证据、导出报告和管理工作空间文件时读本文件。

## 查看、处置与复测

```bash
artexctl findings list --task 123 --status confirmed --severity high
artexctl findings get 789
artexctl findings lineage 789
artexctl findings update 789 --status fixed
artexctl findings retest 789 --notes '用户给定的修复版本、测试条件与范围'
artexctl findings retests 789
```

更新、复测、深入和指定导出使用 standalone `finding_id`，不要误用探索图 node id。复测会启动独立 Agent，deepen 会生成后续任务，实际目标和范围沿用用户授权。

复测结论和执行状态分开读取：复现、已修复、无法确认与 running/failed 等状态不同。完成且结论为已修复时上游会更新漏洞状态；原始证据仍保留。复测历史尚未纳入上游报告/归档包，交付需要时单独读取并保存。

## 流量证据与导出

```bash
artexctl findings traffic 789
artexctl traffic get -q id=TRAFFIC_ID
artexctl findings export --task 123 --export-format md-zip --output evidence.zip
artexctl findings export -q scope=selected -q ids=789,790 --export-format json -o findings.json
artexctl tasks report --task 123 --output report.md
```

`findings export` 默认按筛选导出，scope=all 表示全量，scope=selected 配合逗号分隔 finding IDs。支持 md-single、md-zip、csv、json；md-zip 可带证据包。`tasks report` 是任务 Markdown 报告。

绑定流量用 `findings bind-traffic ID --data @binding.json`；绑定详情、body、编辑、排序与解除关联从 `api list traffic` 选择。流量 exchange ID、漏洞 binding_id 与 finding_id 各自独立。

## 工作空间文件

```bash
artexctl workspace list -q path=tasks/123
artexctl workspace read -q path=tasks/123/notes.txt
artexctl workspace write --set path=tasks/123/notes.txt --content-file notes.txt
artexctl workspace upload -q path=tasks/123 --form file=@notes.txt
artexctl workspace download -q path=tasks/123/report.md --output report.md
```

先从 list 返回的目录确定真实路径，不假定每个任务都在示例目录。upload 的目标目录需已存在，可用 `workspace mkdir --set path=REL` 创建。所有 path 在服务端工作空间内解释；二进制与大文件使用 download。

平台内部技能文件的读写/上传见 [平台管理](administration.md)。流量全量清理与目录删除会实际删除数据，只操作用户指定的对象；下载后按文件实际用途检查内容。
