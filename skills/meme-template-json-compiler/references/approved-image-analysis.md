# Approved Image 独立分析

## 事实边界

视觉语义输入只有 Approved Template Image envelope 和它指向的图片。不读取来源图、换图策略、第一 Skill Prompt、供应商结果、替换池或批次语义。数据台可通过独立 runtime envelope 提供 `existingKey/sourceIdentity`，这些字段只参与注册表查询。

## 分析顺序

先理解模板，再决定字段。顺序固定为：

1. `templateValue`：说明为什么入选、核心玩法、必须固定的机制和后端执行事实。
2. `playDecisionModel`：在看组件清单之前，写出好玩命题、用户重制愿望和核心用户决策。每项决策只映射一个正式槽位。
3. `componentGraph/identityTopology/textRegions`：逐一识别主体、实例、物件、文字、箭头、容器、贴纸、商标、遮挡和背景；文字先按句子、笑话、对比或标签系统聚合为语义单元。
4. `mediumComposition/spatialRelations/containers`：记录画风媒介、构图、光色、动作、接触、持握、穿戴、前后层级和嵌套关系。
5. `editableCandidates/slotCoverageReview`：先对八个候选轴做召回检查，再对每个候选做精度门禁，并给出选中或排除理由。
6. `semanticModel`：从同一个语义模型投影 Prompt Template 和 runtimeSemantics。
7. `selfReview`：对最终草稿重新复核，绑定草稿 SHA，问题修正后重跑。

`templateValue` 至少包含：

- `whySelected`：这张图为什么好玩、有用或值得复用。
- `templateHook`：用户替换什么之后仍能获得原玩法。
- `fixedMechanism`：必须保留的动作、关系、容器、构图或笑点。
- `backendOnlyFacts`：年龄化、完整重绘、媒介统一、实例同步等只应写入后端的事实。

`playDecisionModel` 至少包含：

- `funProposition`：用一句话解释反差、包袱、情绪投射、伪商品包装或其他可复用钩子。
- `userRecreationWish`：用“用户想把……放进……”的用户视角表达重制愿望。
- `coreUserDecisions`：每项包含稳定 `decisionId`、用户选择描述、对应 `slotId` 和图像根据。正式槽位与核心决策一一对账。

## 图像事实与计数

- `visualMechanism`：核心动作、关系、容器、阅读顺序、笑点或视觉钩子。
- `componentGraph`：主体、物体、文字、容器、嵌套内容、背景、贴纸、商标、倒影、剪影和装饰。
- `identityTopology`：身份单元、显示实例、重复身份、固定角色关系和动态群组可能性。
- `textRegions`：每区语言、原文、token、行、数字、标点、符号拓扑、位置、排版、角色和唯一动作。
- `counts`：`identityCount/visualInstanceCount/uploadAssetCount/inputControlCount` 四数独立，由拓扑和正式槽位重新计算。

商标、IP 图标和装饰贴纸先判断它是否承载玩法。只有平台或作者水印默认删除；玩法组成部分默认保留。

## 候选到槽位

每个 `editableCandidate` 都记录 `selected`、`selectionReason` 和 `exclusionReason`。选中理由只能是 `identity_control/template_hook/high_value_text/exact_content_asset`。普通餐食、背景小物和陪衬装饰不能仅因“肉眼可见”就成为槽位。

每个正式槽位在 `slotEvidence` 中保存：六门禁结果、对应 `decisionId`、默认值、语义轴、颗粒度、输入模式决议、推荐项替换检查、binding 决议和 `openVisualFacts`。每个文字槽还保存 `defaultLanguageReview`；身份槽保存 `identityRecognition`，明确当前图是否已识别出具体身份及其通行姓名。能够从服装、发型、标志、画面文字或其他稳定特征确认具体 IP、真人或历史人物时，必须标记为 `recognized`，正式默认值等于具体通行姓名；不得改写为发色、服装、性别等外观描述来规避专名。证据不足时标记为 `unrecognized`，使用简洁的可见身份描述。`openVisualFacts` 是该槽开放后不得被 title、tag 或 visualContract 锁回的身份、文字、服装、颜色或内容事实。

`titleEvidence` 同时证明图像根据、使用动机、口语自然、槽位可迁移、用户吸引力和发现价值。`descriptionEvidence` 证明描述面向用户、补充标题、口语自然且不锁定开放值。每个 `tagEvidence` 项除了图像根据和类别，还要写明 `searchIntent`，表示它承接的真实用户查询。

所有模板都提供 `slotCoverageReview`，逐轴记录 subject、text、object、clothing、color、prop、scene 和 nested content 的候选组件、选中槽位与具体根据。每个正式槽位只在一个主轴出现一次，每个候选组件都被覆盖。正式槽位优先保持在 2–4 个；覆盖评审只得到一个核心用户决策时，单槽合法。超过四个候选时，把次要文字转入 `free_editable`，把普通支持细节保持固定，或合并同一语义轴的控件；不得交付五个及以上槽位。

所有正式槽位都具有文字输入；图片能力只在用户自然拥有素材且输入到目标的映射清楚时附加。固定可寻址主体使用 `one_to_one`；同一身份重复实例使用 `same_source_repeated`。只有整组身份保真、自然合照输入、人数可变、成员同类和无独立角色五项全部为真时使用文字+图片的 `preserve_group`。双人合照、固定 CP 和固定角色位按独立身份拆分。密集同类主体先寻找一个承载玩法的焦点身份；由一个类别概念共同驱动的固定位置集合使用普通文字槽，并由后端保留数量与排列。

## 文字唯一路由

每个文字区只能选 `open_slot/free_editable/preserve/remove/review` 中一项，并保存 `semanticUnitId`、`semanticUnitRole`、`editValue=high/secondary/fixed/none/ambiguous` 与 `routingEvidence`。一句话、一个笑话、一组对比文案或需同步的重复文字即使分布在多个视觉区域，也共享一个语义单元和一个槽位。指向不同人物、可被用户独立改写的标签使用不同语义单元。

`semanticUnitRole` 只使用 `independent_message/distributed_message/supporting_copy/fixed_context/noise/ambiguous`。同一语义单元的文字区必须路由到同一动作；使用 `open_slot` 时必须指向同一个真实文字槽。

`free_editable` 的精确默认文字必须出现在 Prompt Template 的自然叙述中；`preserve` 必须在 visualContract 中保留内容和版式；`remove` 不得进入两个表面；`review` 未解决时阻断编译。这使两种编辑模式共享同一份 Prompt Template，同时保持槽位数量只服务高价值快捷编辑。

翻译区使用 `translation_equivalence`，通过源区/目标区 ID 和各自 exactText SHA 建立等价关系；任何文字变化都会使旧证据失效。

## 共同语义模型

`semanticModel` 是 Prompt Template 与 runtimeSemantics 的共同中间模型。`compile_semantics_from_analysis` 同时投影两者，正式草稿与任一投影发生手工漂移即拒绝。

每个槽位必须在 Prompt Template 中出现一次精确占位符；文字 fallback 与默认值一致。每个 input binding 恰好对应一个正式槽位。每个 identity target 都有完整重绘声明，每个图片槽位都有唯一素材源声明。`openVisualFacts` 不得出现在 visualContract；`backendOnlyFacts` 必须进入 visualContract 且不得进入 Prompt Template。

## 轻量自复核

自复核面向最终 formal draft，而非初版分析。它记录规范化 JSON SHA、全部固定检查项、发现的问题和已应用修订。校验器重新计算 SHA，并要求检查键全集精确、值全部为 true。草稿任何字段变化都会使旧复核失效。

复核重点包括好玩命题与用户重制愿望、槽位召回覆盖、槽位精度、语义单元一致性、图片输入理由、群组合理性、身份特征权限的完整性与最小模板例外，文字槽位/自由编辑/固定层路由，默认值是否自然且优先使用已识别身份、title 和 description 的用户价值、Prompt 前台可读性、占位符、推荐项、Tags 的正式大类与检索意图，以及 visualContract 的开放值隔离。该步骤不产生新图片、不调用外部 API，也不代替人工审核。
