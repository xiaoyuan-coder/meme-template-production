# 便携产物与批量隔离

一个生产任务可接受 1–5000 项。先用 `plan_production_job` 按默认 50 项拆成稳定执行分片；每个分片保持 1–100 项。每项拥有独立 `itemId/revision/state/stage/errorCode/evidence/recoveryAction`。拒绝、策略阻断、技术失败或费用/API 异常只更改当前项，其他项与分片继续。

非对象输入也形成当前位置的 `ITEM_NOT_OBJECT` 结果。异常通过稳定 `errorCode` 与固定脱敏摘要投影；原始异常字符串、URL、token、环境变量值和供应商响应不写入批次状态。

通用产物使用 URI，不写本机绝对路径。建议的外部运行布局是：

```text
<runtime-root>/
  sidecars/<itemId>/                 # 策略、generation attempt、审核和恢复状态
  sidecars/job/plan.json             # 全任务 item 顺序与执行分片
  sidecars/job/diversity.json        # 全任务候选分配、指纹次数与可避免集中项
  sidecars/reviews/                  # 对话框批量策略表与前后缩略图清单
  receipts/<itemId>/oss-receipt.json # 图片 Skill 私有上传凭据
  approved/<itemId>/approved-image.json
  index/production-index.json        # 稳定扫描入口
```

`production-index.json` 遵循 bundled `production-index.schema.json`。每次进入策略审核、图片审核、上传或已完成状态时，通过 `write_production_index` 原子合并当前 `(skill,itemId,revision)`。产物引用使用 `artifact://` 或 `sidecar://`，由个人数据台映射到自身存储。个人数据台的页面、数据库、机器人、路径和业务索引不进入本 Skill。

多样性报告覆盖完整生产任务，并在任何单项策略编译前生成。可避免的集中项先重新分配候选，再形成对话框策略表。两个人工点均按分片集中展示：策略点是一张替换表，成图点是前后缩略图表；回复可以批准全部或排除 item ID。对话框决策落成逐项审批事实，便于单项恢复。
