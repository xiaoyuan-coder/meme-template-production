# Approved Image 独立分析

## 事实边界

视觉语义输入只有 Approved Template Image envelope 和它指向的图片。不读取来源图、换图策略、第一 Skill Prompt、供应商结果、替换池或批次语义。数据台可通过独立 runtime envelope 提供 `existingKey/sourceIdentity`，这些字段只参与注册表查询。

## 分析对象

完成 `approved-image-analysis` 后再写 Gallery 字段。分析至少覆盖：

- `visualMechanism`：核心动作、关系、容器、阅读顺序、笑点或视觉钩子。
- `componentGraph`：主体、物体、文字、容器、嵌套内容、背景、贴纸、商标、倒影、剪影和装饰。
- `identityTopology`：身份单元、显示实例、重复身份、固定 CP/家庭/组合、动态群组可能性。
- `textRegions`：每区语言、原文、token、行、大小写、数字、标点、符号拓扑、位置、排版、角色和唯一动作。
- `mediumComposition`：媒介、风格特征、构图、色彩与光线。
- `spatialRelations/containers`：动作、接触、遮挡、前后层级、持握、穿戴、容器嵌套和独立内容。
- `fixedStructure/editableCandidates`：只读结构与高价值可编辑轴。
- `counts`：`identityCount/visualInstanceCount/uploadAssetCount/inputControlCount` 四数独立。

每个正式字段在 `fieldEvidence` 拥有独立的图像根据。必备证据键由 machine contract 冻结，覆盖 key、title、description、tags、imageSize、槽位、推荐、默认值、文字、主体/身份绑定、Prompt Template、visualContract、inputBindings、clothingOwnership、cover 和 referenceImage。

## 确定性交叉验证

- `singleSlotExhaustion` 逐轴记录 subject、text、object、clothing、color、prop、scene、nested content 的候选结论，选中槽位与 `inputSchema.slots` 完全一致。
- `translationEquivalences` 通过源区/目标区 ID 和各自 exactText SHA 建立等价关系；任何文字变化都会使旧证据失效。
- `semanticModel` 是 Prompt Template 与 runtimeSemantics 的共同中间模型。`compile_semantics_from_analysis` 同时投影两者，正式草稿与任一投影发生手工漂移即拒绝。
- `componentCoverage` 把每个 componentGraph 节点投影到 targetInstances 与 visualContract 字段，并要求两侧全集覆盖。
- 每个 identity target 都有 `completeRedrawByTarget=true`；每个图片槽位都有唯一 `sourceIsolationByInput=true`；每个开放值只有一个 `dynamicFactSources=inputSchema.slots.<slotId>`。
- 四项 counts 由 identityTopology、实例 ID、图片槽位与全部槽位重新计算，不接受调用方自报值。

## 文字唯一路由

每个文字区只能选 `open_slot/free_editable/preserve/remove/review` 中一项。水印删除，歧义文字待审。身份文字、主视觉文字和高价值短 span 才参与槽位评估。次要可读内容进入 `free_editable` 并出现在 Prompt Template；装饰微字、版权和出处信息固定或清理。翻译区使用 `translation_equivalence`，源文更改后重算译文。
