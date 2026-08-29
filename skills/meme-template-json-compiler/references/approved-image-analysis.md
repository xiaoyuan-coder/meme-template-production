# Approved Image 独立分析

## 事实边界

视觉语义输入只有 Approved Template Image envelope 和它指向的图片。不读取来源图、换图策略、第一 Skill Prompt、供应商结果、替换池或批次语义。数据台可通过独立 runtime envelope 提供 `existingKey/sourceIdentity`，这些字段只参与注册表查询。

## 分析顺序

先理解模板，再决定字段。顺序固定为：

1. `templateValue`：说明为什么入选、核心玩法、必须固定的机制和后端执行事实。
2. `componentGraph/identityTopology/textRegions`：逐一识别主体、实例、物件、文字、箭头、容器、贴纸、商标、遮挡和背景。
3. `mediumComposition/spatialRelations/containers`：记录画风媒介、构图、光色、动作、接触、持握、穿戴、前后层级和嵌套关系。
4. `editableCandidates`：逐候选判断它是否直接服务模板玩法，并给出选中或排除理由。
5. `semanticModel`：从同一个语义模型投影 Prompt Template 和 runtimeSemantics。
6. `selfReview`：对最终草稿重新复核，绑定草稿 SHA，问题修正后重跑。

`templateValue` 至少包含：

- `whySelected`：这张图为什么好玩、有用或值得复用。
- `templateHook`：用户替换什么之后仍能获得原玩法。
- `fixedMechanism`：必须保留的动作、关系、容器、构图或笑点。
- `backendOnlyFacts`：年龄化、完整重绘、媒介统一、实例同步等只应写入后端的事实。

## 图像事实与计数

- `visualMechanism`：核心动作、关系、容器、阅读顺序、笑点或视觉钩子。
- `componentGraph`：主体、物体、文字、容器、嵌套内容、背景、贴纸、商标、倒影、剪影和装饰。
- `identityTopology`：身份单元、显示实例、重复身份、固定角色关系和动态群组可能性。
- `textRegions`：每区语言、原文、token、行、数字、标点、符号拓扑、位置、排版、角色和唯一动作。
- `counts`：`identityCount/visualInstanceCount/uploadAssetCount/inputControlCount` 四数独立，由拓扑和正式槽位重新计算。

商标、IP 图标和装饰贴纸先判断它是否承载玩法。只有平台或作者水印默认删除；玩法组成部分默认保留。

## 候选到槽位

每个 `editableCandidate` 都记录 `selected`、`selectionReason` 和 `exclusionReason`。选中理由只能是 `identity_control/template_hook/high_value_text/exact_content_asset`。普通餐食、背景小物和陪衬装饰不能仅因“肉眼可见”就成为槽位。

每个正式槽位在 `slotEvidence` 中保存：四门禁结果、默认值、语义轴、颗粒度、输入模式决议、推荐项替换检查、binding 决议和 `openVisualFacts`。每个文字槽还保存 `defaultLanguageReview`；身份槽保存 `identityRecognition`，明确当前图是否已识别出具体身份及其通行姓名。识别为具体 IP、真人或历史人物时，正式默认值必须等于该姓名；未识别时才使用简洁的可见身份描述。`openVisualFacts` 是该槽开放后不得被 title、tag 或 visualContract 锁回的身份、文字、服装、颜色或内容事实。

只有一个槽位时才提供 `singleSlotExhaustion`，逐轴记录 subject、text、object、clothing、color、prop、scene 和 nested content 的候选结论；多槽任务不生成这份仪式性证明。

固定可寻址主体使用 `one_to_one`；同一身份重复实例使用 `same_source_repeated`。只有整组身份保真、自然合照输入、人数可变、成员同类和无独立角色五项全部为真时使用 `preserve_group`。密集同类主体先寻找一个承载玩法的焦点身份；其余保持固定或抽象为文字内容，不能直接升级为动态群组。

## 文字唯一路由

每个文字区只能选 `open_slot/free_editable/preserve/remove/review` 中一项。`open_slot` 必须指向一个真实存在、具备文字输入的 slot ID。人物上方箭头标签、关系称呼、对话、主标题等高价值文字分别开放；两段指向不同人的文字不可合并。水印删除，歧义文字待审，装饰微字保留或清理。

翻译区使用 `translation_equivalence`，通过源区/目标区 ID 和各自 exactText SHA 建立等价关系；任何文字变化都会使旧证据失效。

## 共同语义模型

`semanticModel` 是 Prompt Template 与 runtimeSemantics 的共同中间模型。`compile_semantics_from_analysis` 同时投影两者，正式草稿与任一投影发生手工漂移即拒绝。

每个槽位必须在 Prompt Template 中出现一次精确占位符；文字 fallback 与默认值一致。每个 input binding 恰好对应一个正式槽位。每个 identity target 都有完整重绘声明，每个图片槽位都有唯一素材源声明。`openVisualFacts` 不得出现在 visualContract；`backendOnlyFacts` 必须进入 visualContract 且不得进入 Prompt Template。

## 轻量自复核

自复核面向最终 formal draft，而非初版分析。它记录规范化 JSON SHA、全部固定检查项、发现的问题和已应用修订。校验器重新计算 SHA，并要求检查键全集精确、值全部为 true。草稿任何字段变化都会使旧复核失效。

复核重点包括模板价值、槽位最小化、图片输入理由、群组合理性、文字路由、默认值是否自然且优先使用已识别身份、title 可迁移性、Prompt 前台可读性、占位符、推荐项、正式大类 Tag 和 visualContract 的开放值隔离。该步骤不产生新图片、不调用外部 API，也不代替人工审核。
