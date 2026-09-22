---
name: meme-template-json-compiler
description: 将用户批准的本地图片或已上传模板图独立分析为可复用的 Gallery v2 模板 JSON，支持直接从本 Skill 开始。用于模板玩法分析、可编辑槽位设计、模板文案与运行语义编译、按名称或 key 定位当前模板、批量交付及 JSON 局部返修。
---

# 模板 JSON 编译器

把一张已批准的图片变成用户愿意使用的模板：标题和描述让人理解玩法，槽位让人方便地做出“我的版本”，生成结果继续保留原图的趣味、关系、构图和媒介。

同一模板支持槽位输入和完整 Prompt 自由编辑。两种模式共享运行约束，用户指定的内容应准确生效，模板机制保持可辨认。

## 输入与职责

支持两种输入：用户在当前对话中明确批准的本地 PNG，以及 Approved Template Image v2 envelope 所指向的已批准图片。视觉语义只来自选定图片。独立查看该图，不消费来源图分析、替换策略、生成提示词、供应商数据或批次推理。Key 是模板身份；源身份只作来源证据。

本 Skill 交付正式 `<key>.json`：`cover`、`referenceImage` 原样复用输入 URL，首次与返修均省略 `imageUrl`。上游路径的模板图生产与上传由第一 Skill 负责；直接入口通过本 Skill 的适配器发布已批准原图，不调用图像生产。氛围图由 `template-atmosphere-image-producer` 负责。

## 任务路由

先判断任务类型，再读取对应资料：

- **修改已有模板数据**：先读取 [current-version-registry.md](references/current-version-registry.md) 和 [返修与读回校验.md](references/返修与读回校验.md)。用名称或已知 key 定位 `templateDataRoot` 中的 current 正式 JSON，再判断采用轻量数据修订或完整重分析。截图提供视觉证据，不承担数据寻址。
- **从本地图片创建模板**：读取 [direct-input.md](references/direct-input.md)。用户已明确批准该图片时记录批准证据，进入独立分析；正式交付前按适配流程发布原图，在 `templateDataRoot` 中建立新 key。
- **从已上传图片创建模板**：通过 `validate_approved_image_envelope` 校验 v2 `approved_uploaded` envelope，随后进入主流程。
- **核对工作台最新版本**：仅在用户要求工作台同步或读回时，采集列表、详情、编辑预览和导出数据。该分支不阻塞便携正式交付。

缺少依赖时报告所缺项，不自动安装。两个新建入口共用全部视觉分析、语义复核和正式编译门禁。参考图实际尺寸保存于 envelope；生成画布 `imageSize` 由 `select_generation_image_size` 选择，不修改参考图字节。

## 主流程

### 1. 明确用户想重制什么

读取 [product-model.md](references/product-model.md)、[play-mechanism-review.md](references/play-mechanism-review.md) 和 [approved-image-analysis.md](references/approved-image-analysis.md)。先查看图片，完成玩法机制的视觉证据与反事实检查，形成 `templateValue` 与 `playDecisionModel`，再进入组件盘点和槽位设计。

说清楚：图片为什么有趣或值得使用，用户想把自己的什么放进去，主动改变哪些内容，以及哪些机制使改后的图仍然成立。按分析合同记录主体、身份单元、文字、动作关系和空间结构，为后续取舍提供图像证据。

完成标准：能用原图的具体部位证明核心关系，说明失去该关系会怎样改变玩法，并说明替换输入时需要共同变化的部位。仅有组件清单、情绪词或画风名称时，继续观察，暂不编写模板草稿；局部关系看不清时查看原尺寸或放大该区域。

### 2. 选择最小有用的控制集合

读取 [slot-decision-cases.md](references/slot-decision-cases.md) 和 [authoring-fields.md](references/authoring-fields.md)。先逐轴召回主体、文字、物件、服装、颜色、道具、场景和嵌套内容，再用六项条件筛选：用户动机、独立选择、明显变体、结果可见、模型可控、机制保持。先把颜色、形状、材质和图案还原到它们共同修饰的完整视觉对象；用户会整体替换的外框、容器、包装或协调装饰组优先作为一个控制，再判断是否进入正式槽位。

每个槽位对应一个可执行控制，通常为 1–4 个；覆盖评审证明第五个也具有独立高价值时，允许 5 槽。背景是必查候选轴：先识别纯色或渐变、花纹、材质纹理、场景、嵌套区域和与主体融合的背景，再按用户编辑价值决定是否成为正式槽位。不为背景预留固定席位。图片能力取决于用户素材到目标的映射。

一句话、一个笑话或一套标签先按语义单元处理，空间分散不单独构成拆槽理由。同一使用意图涉及独立后端绑定时保留独立控制，说明语义关联，不宣称输入会自动同步。

### 3. 从同一玩法编写模板

读取 [tags.md](references/tags.md)、[template-tagging-prompt.md](references/template-tagging-prompt.md) 与 [visual-contract.md](references/visual-contract.md)。标签先从图像分别产出 `hiddenTags` 和 `keywords`，再通过 `merge_template_discovery_tags` 按固定顺序合并为 `metadata.tags`；可确定的宠物类型必须保留具体动物词，排除“白底摄影”“白底图标”等低检索价值的呈现标签。视觉约束须从原图提取具体媒介、造型、线条、着色与纹理规则，明确全图或分区适用范围，并说明新身份如何在该画法下重绘；画风名称本身不足以完成约束。`mediumComposition` 保存选定的稳定规则，媒介及条目按视觉规范与最终字段逐项对应。

按字段规范同时形成三个一致的表达：`promptTemplate` 让用户看懂怎么改，`inputSchema` 提供操作入口，`runtimeSemantics` 保持模板机制并绑定输入目标。

- 每槽可选、支持自定义文字，并有三个与默认值同轴、同颗粒度、同语言及表达形式的推荐项；图片是附加能力。
- Prompt Template 只描述开放给用户修改的画面内容，用容易理解的自然语言完整覆盖槽位与低频自由编辑项，每个槽位恰好出现一次。槽位 label 使用最小充分名称，如“主体”“画面主体”“底部文字”“背景”，避免被当前默认值限定。媒介、画风、质感、光线和固定空间机制进入 visualContract。
- 完成逐元素路由对账：`componentGraph` 中每个可见元素都明确进入槽位、Prompt 自由编辑、visualContract 固定实现或清理四类路由之一。没有进入槽位的颜色、形状、图案、装饰、容器内容和次要文字，只要允许用户改动，就以当前默认外观进入 Prompt 并建立 `editableFactRouting`。
- 为每项可编辑事实建立 `editableFactRouting`，明确它属于 Prompt 或某个槽位，列出 visualContract 中禁止残留的旧值及同义表达，并将包装顶部食物这类联动部件全部纳入 binding 依赖目标。
- 标题、描述和标签共同表达模板价值与使用动机，避免组件清单和编译术语。

文字长度与语义路由、已识别身份命名、图片输入配置、身份特征权限及标签数量，逐项执行字段规范。完成时，每个开放内容有编辑路径，每个槽位有对应 binding，固定约束有模板机制依据。

### 4. 解析 key，校验并自复核

读取 [key-registry.md](references/key-registry.md)，通过 `resolve_template_key(templateDataRoot, proposedKey, existing_key=...)` 取得决议。新建 key 必须未被占用；返修显式复用已有 key。标题、图片、来源身份和 SHA 都不改变 key 身份。

读取 [gallery-v2.md](references/gallery-v2.md)，按固定 Schema 与生产约束校验草稿。执行分析规范中的同轮 self-review：每项有具体证据，绑定最终草稿 SHA；修改后重新复核。

语义复核需实际代入不同推荐值，检查新内容能否生效、玩法是否保留、其他字段是否仍锁定旧内容。机器校验与语义判断分别完成。全部通过后，首次编译调用 `compile_final_json`，换图或完整重分析返修调用 `compile_template_revision`，不换图的 JSON 返修调用 `compile_json_revision` 或轻量入口。

### 5. 交付正式数据

每次交付读取 [portable-delivery.md](references/portable-delivery.md)。调用 `write_formal_json` 和 `write_production_index` 保留本次运行证据，再调用 `publish_template(templateDataRoot, formal, ...)` 产生自包含历史并原子替换同 key current。用户未指定时要求选择一个可持久化的 `templateDataRoot`；工作台不是交付前置条件。

报告已交付 key、revision、历史入口与 `templateDataRoot` current 状态。涉及工作台的任务继续执行可选读回分支；便携正式交付与工作台更新分别确认。

## 条件分支

### JSON 返修

按名称或 key 调用 `locate_current_template` 取得 `templateDataRoot` 中的 current 正式 JSON 和请求证据。若该 key 尚未进入便携数据根，按 current 规范执行一次性基线登记；候选版本存在冲突时列出候选并请用户确认。修改前声明 scope，以完整上一版摘要绑定；保留未涉及的槽位、绑定和字段。

标题、描述、标签、槽位、Prompt 或运行语义的定向修复，在现有正式 JSON 仍符合 v2 图片地址合同时，完成图像证据与四项修订复核后调用 `compile_data_revision`，无需重新执行本地图片准入、上传和完整分析。玩法结构不清、需要新增或重构控制、或用户要求换图时，沿主流程重建完整证据并调用 `compile_template_revision`。

key 解析需确认 `EXISTING_KEY`，发布时提供编辑基线的 current SHA。上一版含氛围图字段时保持原对象只读，新产物遵循本 Skill 的字段边界。现有正式对象不符合当前合同且修复范围超出用户请求时，报告具体合同差异并请求迁移策略，不自行引入环境名称或地址迁移规则。用户提供新批准原图时走直接入口；需要生成新图时转回第一 Skill。

### 工作台读回

用户要求同步或核对工作台时，读取 [返修与读回校验.md](references/返修与读回校验.md)。以 `templateDataRoot` current 为基准采集工作台实际观察，再调用 `validate_delivery_readback` 校验列表、详情、编辑预览和导出。

选版与读回均通过后才报告工作台已更新。入口不可用或内容过期时保留正式交付，标注读回待完成；较新的未交付修改继续显示待处理状态。

### 批量生产

按确定的 1–100 项分片执行，保持每项分析、key 决议、交付和错误独立。一项失败只暂停该项，其余继续；恢复使用该项记录的阶段与原因。打包和安装验证属于 Skill 维护，不进入普通模板生产流程。
