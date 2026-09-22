# Agent 工作约定

本文件适用于 `meme-template-json-compiler` 目录及其子目录。功能与运行方式见 [README.md](README.md)；执行任务时先读取 [SKILL.md](SKILL.md)，按任务分支加载对应参考资料。

## 任务边界

- 从已批准图片独立建立视觉语义。来源图分析、替换策略和生成提示词不作为分析输入。
- Key 是模板身份；源身份和图片 SHA 只作来源与完整性证据。
- 已有模板按名称或 key 定位，稳定 `templateDataRoot` 决定正式当前版本；截图和图片 URL 不参与数据寻址。
- `templateDataRoot` 由第二 Skill 自主维护，工作台为可选消费方。本仓库内的本地数据只放入被忽略的 `local-data/`、`runs/` 或 `outputs/`。
- 正式交付仅包含本 Skill 的字段。`cover`、`referenceImage` 复用已验证 envelope 的 URL；直接本地入口见 `references/direct-input.md`；`imageUrl` 由氛围图 Skill 管理。

## 分析与编译

- 先明确模板价值和用户重制愿望，再盘点组件与槽位。
- 槽位选择同时满足用户动机、独立选择、明显变体、结果可见、模型可控和机制保持。通常为 1–4 槽，第五槽需有独立高价值证据；背景必须召回评估，依据编辑价值决定是否开槽。
- 每槽支持文字、自定义输入和三个推荐项；图片能力按目标映射决定。
- Prompt Template、槽位和运行语义来自同一分析，保持输入绑定及可编辑内容一致。槽位优先控制完整视觉对象或同职能装饰组；`componentGraph` 每个元素在 `promptCoverage.visualElementRoutes` 中恰好有一条路由。
- 首次使用 `compile_final_json`，不换图返修使用 `compile_json_revision`，换图或完整重构使用 `compile_template_revision`。校验后再写入正式数据，草稿变化后重新执行自复核。

## 返修与交付

- 修改范围从用户请求确定，以完整上一版 JSON 摘要绑定；未涉及的字段、槽位和绑定保持原值。
- 现有 v2 正式 JSON 的定向数据修订优先使用 `compile_data_revision`；合同外迁移需要用户或既有合同明确授权。
- 上一版作为只读基线。新修订使用独立交付位置，正式模板目录仅保留一个 `<key>.json`。
- 历史交付和生产索引写入后，用 `publish_template` 原子替换同 key current；工作台只消费摘要校验通过的 current object。
- current 缺失时只登记一个已验证的权威基线；多个不同候选交由用户或数据台确认。
- 分析、自复核、注册表证据和运行状态放在正式模板目录之外。
- key 冲突、校验失败或写入冲突只暂停当前项，按对应原因恢复。
- 工作台读回使用真实采集的列表、详情、编辑预览和导出数据；交付完成与读回完成分别报告。

## 维护与验证

字段白名单和确定性约束以 `references/machine-contract.json` 为准，Schema 使用随包携带的固定版本。合同变更同步编译器、引用文档和相关测试；保留已有不可变 snapshot。

修改代码或合同后，在本目录运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

在完整源码仓库中，同时执行仓库要求的相关回归与 Skill 格式检查。匿名示例只用于测试；生产证据取自实际图片、请求及工作台观察。
