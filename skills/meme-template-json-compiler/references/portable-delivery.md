# 正式交付、sidecar 与索引 seam

每个执行分片支持 1–100 项；生产任务可由上游规划为多个分片。每项独立保存状态和恢复动作。数据根不可读、key 冲突、语义门禁或写文件冲突只暂停当前项。

非对象输入也形成当前位置的 `ITEM_NOT_OBJECT` 结果。异常通过稳定 `errorCode` 与固定脱敏摘要投影；原始异常字符串、URL、token、环境变量值和供应商响应不写入批次状态。

建议的外部运行布局是：

```text
<runtime-root>/
  delivery/<key>/<key>.json           # 目录内只有这一个裸对象
  sidecars/<itemId>/                  # analysis、self-review、key 证据和状态
  sidecars/batch/identity-diversity.json # 已识别身份分布和重复异常
  index/production-index.json         # 个人数据台稳定扫描入口
```

`write_formal_json` 的参数是 `<runtime-root>/delivery`。`write_production_index` 写入 index 兄弟目录。索引引用只使用 `artifact:// / delivery:// / sidecar://`，不携带本机绝对路径。个人数据台负责 URI 映射、页面、数据库和宽松/严格索引；本 Skill 只交付便携合同。

`runtime-root` 保存一次运行证据，`templateDataRoot` 保存跨运行复用的正式模板数据。两者使用独立路径。仓库内的兼容位置分别为被忽略的 `runs/` 与 `local-data/template-data/`；工作台只是可选读取方。

稳定索引按 `(skill, itemId, revision)` 合并：同一三元组由新状态原子替换，新 revision 追加保留；`generatedAt` 随成功写入更新。写入使用进程锁、同目录临时文件、fsync 和 rename，并拒绝损坏旧索引、符号链接与越界路径。每次调用仍受 1–100 条批量边界约束。

完整任务的分析结果通过 `build_batch_identity_diversity_report` 生成已识别身份分布，供生产质量追踪和后续选题复盘。每项通过确定性语义门禁与同轮 self-review 后，直接运行 `compile_final_json` 并写入交付目录。模板数据看板展示最终数据并承接返修；JSON 编译过程没有额外人工批准状态；本地直接入口的原图发布发生于正式编译前，遵守 [direct-input.md](direct-input.md)。

## 状态续跑与看板读回

JSON-only revision 以现有 `approved_uploaded` envelope、当前 key 和上一版正式 JSON 为基线。新 revision 明确记录新增、删除和修改的 slot ID；未列入变更范围的槽位、主体拓扑、`cover`、`referenceImage` 和 key 保持原值；第二阶段新产物省略 `imageUrl`，原交付中的氛围图字段继续由第三 Skill 和数据台保管。通过 `compile_json_revision` 校验变更范围后交付，调用合同见 [返修与读回校验.md](返修与读回校验.md)。需要换模板图的 item 按 SKILL.md 选择用户批准原图的直接入口或第一 Skill 生图入口；需要新氛围图的 item 进入第三 Skill；其余 item 继续 JSON 编译。

### 当前正式版本与可选工作台读回

`templateDataRoot` 的 current 就是第二 Skill 的正式结果。返修交付完成后，同 key 的列表、详情、槽位编辑预览和 JSON 导出应采用同一条 current record 的 `objectRef`；旧版本保留在 history。完整合同见 [current-version-registry.md](current-version-registry.md)。

- 当前版本由 `current-template-registry.json` 的 key 记录确定。索引 `generatedAt` 是整份历史索引的更新时间，文件修改时间、扫描顺序、图片 URL 和跨批次的局部 revision 数字都不证明某个 key 更新。
- 新修改尚在分析、校验失败、写入失败或等待换图批准时，显示“有新修改待交付”及对应状态。需要展示上一版时，明确标注“上一版已交付”，避免将其标为最新修改结果。
- 每个新 revision 使用独立交付位置，沿用 create-once 写入并保留历史。先完成正式 JSON 与索引写入，再用带上一版摘要的 `publish_template` 切换当前引用；同一视图中的标题、描述、槽位、推荐项、Prompt、运行语义和图片引用共同来自该 revision。
- JSON-only 修订继续复用已批准图片 URL，数据新鲜度通过正式 JSON 与修订记录核对。图片 URL 未变化不能作为跳过刷新或读回的依据。

`publish_template` 成功表示便携正式数据已更新。任务另行要求进入模板数据看板时，再由本地数据台按其授权入口完成真实读回：

- runtime root 位于或已登记到正式扫描范围；
- 每个 key 的当前交付引用指向本次应采用的修订记录与正式 JSON；
- 列表、详情、编辑预览和导出均采用该版本，导出 JSON 与正式交付 JSON 的规范化内容一致；本轮修改的字段逐项一致，已删除槽位及旧推荐项没有残留；
- 来源素材、Approved Template Image 和正式 JSON 均可解析；
- 专题下唯一 item/key 数与生产账本一致；
- 缺失产物、重复 key 和错误 URI 为零。

读回证据保存在 sidecar 或本地数据台记录中，至少包含 key、修订身份、正式 JSON 引用与内容摘要、读回时间和各入口核对结果。只有全部符合时才报告“工作台已更新到最新交付”。数据台不可用或仍读到旧版时，报告“便携交付完成、工作台最新版本读回待完成”，并给出 `production-index.json` 入口和受影响的 key。生产 Skill 保持便携交付边界，工作台刷新与读回由本地数据台执行。

正式 `<key>.json` 不包含顶层 `id`、sidecar、receipt、审核、路径、API 响应或运行状态。顶层模板 `id` 只由后端入库生成；已上线数据从管理台导出时可能带有该字段，不能据此写回生产交付。`inputSchema.slots[].id` 与 `runtimeSemantics.targetInstances[].id` 是模板内部绑定标识，继续保留。删除 sidecar 不改变已交付 JSON 的运行语义。

## 2026-09-08 字段归属调整

第二阶段的交付与读回比较只覆盖自身字段，均省略 `imageUrl`。工作台采集观察时显式去除第三阶段字段，再交给 `validate_delivery_readback`。研发入库采用第二阶段字段投影更新；缺省 `imageUrl` 表示本阶段不提供该字段，不应据此清空数据库已有氛围图。需要输出带氛围图的完整版本时，由第三 Skill 使用已有有效回执重新完成回填与读回，无须由第二 Skill 携带地址。

正式 JSON 写入通过同文件系统硬链接原子创建目标，已有同内容文件幂等复用，已有不同内容报冲突；临时文件位于交付根目录，完成或失败均清理。目标所在文件系统需要支持硬链接，macOS/Linux 本地文件系统适用。
