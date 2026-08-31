# 正式交付、sidecar 与索引 seam

每个执行分片支持 1–100 项；生产任务可由上游规划为多个分片。每项独立保存状态和恢复动作。注册表不可用、key 冲突、语义门禁或写文件冲突只暂停当前项。

非对象输入也形成当前位置的 `ITEM_NOT_OBJECT` 结果。异常通过稳定 `errorCode` 与固定脱敏摘要投影；原始异常字符串、URL、token、环境变量值和供应商响应不写入批次状态。

建议的外部运行布局是：

```text
<runtime-root>/
  delivery/<key>/<key>.json           # 目录内只有这一个裸对象
  sidecars/<itemId>/                  # analysis、self-review、registry 证据和状态
  sidecars/batch/identity-diversity.json # 已识别身份分布和重复异常
  index/production-index.json         # 个人数据台稳定扫描入口
```

`write_formal_json` 的参数是 `<runtime-root>/delivery`。`write_production_index` 写入 index 兄弟目录。索引引用只使用 `artifact:// / delivery:// / sidecar://`，不携带本机绝对路径。个人数据台负责 URI 映射、页面、数据库和宽松/严格索引；本 Skill 只交付便携合同。

稳定索引按 `(skill, itemId, revision)` 合并：同一三元组由新状态原子替换，新 revision 追加保留；`generatedAt` 随成功写入更新。写入使用进程锁、同目录临时文件、fsync 和 rename，并拒绝损坏旧索引、符号链接与越界路径。每次调用仍受 1–100 条批量边界约束。

完整任务的分析结果通过 `build_batch_identity_diversity_report` 生成已识别身份分布，供生产质量追踪和后续选题复盘。每项通过确定性语义门禁与同轮 self-review 后，直接运行 `compile_final_json` 并写入交付目录。模板数据看板展示最终数据并承接返修；编译过程没有人工批准状态，也不访问 OSS。

正式 `<key>.json` 不包含顶层 `id`、sidecar、receipt、审核、路径、API 响应或运行状态。顶层模板 `id` 只由后端入库生成；已上线数据从管理台导出时可能带有该字段，不能据此写回生产交付。`inputSchema.slots[].id` 与 `runtimeSemantics.targetInstances[].id` 是模板内部绑定标识，继续保留。删除 sidecar 不改变已交付 JSON 的运行语义。
