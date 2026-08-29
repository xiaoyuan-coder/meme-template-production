# 便携产物与批量隔离

单批接受 1–100 项。每项拥有独立 `itemId/revision/state/stage/errorCode/evidence/recoveryAction`。拒绝、策略阻断、技术失败或费用/API 异常只更改当前项，其他项继续。

非对象输入也形成当前位置的 `ITEM_NOT_OBJECT` 结果。异常通过稳定 `errorCode` 与固定脱敏摘要投影；原始异常字符串、URL、token、环境变量值和供应商响应不写入批次状态。

通用产物使用 URI，不写本机绝对路径。建议的外部运行布局是：

```text
<runtime-root>/
  sidecars/<itemId>/                 # 策略、generation attempt、审核和恢复状态
  approved/<itemId>/approved-image.json
  index/production-index.json        # 稳定扫描入口
```

`production-index.json` 遵循 bundled `production-index.schema.json`。每次进入策略审核、图片审核或已批准状态时，通过 `write_production_index` 原子合并当前 `(skill,itemId,revision)`。产物引用使用 `artifact://` 或 `sidecar://`，由个人数据台映射到自身存储。个人数据台的页面、数据库、机器人、路径和业务索引不进入本 Skill。
