---
name: meme-template-json-compiler
description: 将已审核并上传的模板图独立分析为可复用的 Gallery v2 模板 JSON。用于模板玩法分析、可编辑槽位设计、模板文案与运行语义编译、批量交付及 JSON 局部返修。
---

# 模板 JSON 编译器

把一张已批准的图片变成用户愿意使用的模板：标题和描述让人理解玩法，槽位让人方便地做出“我的版本”，生成结果继续保留原图的趣味、关系、构图和媒介。

同一模板支持槽位输入和完整 Prompt 自由编辑。两种模式共享运行约束，用户指定的内容应准确生效，模板机制保持可辨认。

## 输入与职责

视觉语义只来自 Approved Template Image v2 envelope 所指向的已批准图片。独立查看该图，不消费来源图分析、替换策略、生成提示词、供应商数据或批次推理。数据台可另行提供 runtime envelope，源身份仅用于 key 解析。

本 Skill 交付正式 `<key>.json`：`cover`、`referenceImage` 原样复用输入 URL，首次与返修均省略 `imageUrl`。模板图生产与上传由第一 Skill 负责，氛围图由 `template-atmosphere-image-producer` 负责。

## 开始前

确认 `requirements.txt` 声明的依赖可用，再调用 `scripts/compiler.py`；缺少依赖时报告所缺项，不自动安装。通过 `validate_approved_image_envelope` 校验 v2 `approved_uploaded` envelope 及不可变 URL。

首次编译直接进入主流程。局部返修先执行下文“JSON 返修”的基线与范围准备，再沿主流程重建证据。

## 主流程

### 1. 明确用户想重制什么

读取 [product-model.md](references/product-model.md)、[play-mechanism-review.md](references/play-mechanism-review.md) 和 [approved-image-analysis.md](references/approved-image-analysis.md)。先查看图片，完成玩法机制的视觉证据与反事实检查，形成 `templateValue` 与 `playDecisionModel`，再进入组件盘点和槽位设计。

说清楚：图片为什么有趣或值得使用，用户想把自己的什么放进去，主动改变哪些内容，以及哪些机制使改后的图仍然成立。按分析合同记录主体、身份单元、文字、动作关系和空间结构，为后续取舍提供图像证据。

完成标准：能用原图的具体部位证明核心关系，说明失去该关系会怎样改变玩法，并说明替换输入时需要共同变化的部位。仅有组件清单、情绪词或画风名称时，继续观察，暂不编写模板草稿；局部关系看不清时查看原尺寸或放大该区域。

### 2. 选择最小有用的控制集合

读取 [slot-decision-cases.md](references/slot-decision-cases.md) 和 [authoring-fields.md](references/authoring-fields.md)。先逐轴召回主体、文字、物件、服装、颜色、道具、场景和嵌套内容，再用六项条件筛选：用户动机、独立选择、明显变体、结果可见、模型可控、机制保持。

每个槽位对应一个可执行控制，通常为 2–4 个；完整覆盖审查证明只有一个核心控制时允许单槽，最多四槽。其余内容明确归入自由编辑或固定机制。图片能力取决于用户素材到目标的映射，身份单元与重复实例按分析合同区分。

一句话、一个笑话或一套标签先按语义单元处理，空间分散不单独构成拆槽理由。同一使用意图涉及独立后端绑定时保留独立控制，说明语义关联，不宣称输入会自动同步。

### 3. 从同一玩法编写模板

读取 [tags.md](references/tags.md) 与 [visual-contract.md](references/visual-contract.md)。视觉约束须从原图提取具体媒介、造型、线条、着色与纹理规则，明确全图或分区适用范围，并说明新身份如何在该画法下重绘；画风名称本身不足以完成约束。`mediumComposition` 保存选定的稳定规则，媒介及条目按视觉规范与最终字段逐项对应。

按字段规范同时形成三个一致的表达：`promptTemplate` 让用户看懂怎么改，`inputSchema` 提供操作入口，`runtimeSemantics` 保持模板机制并绑定输入目标。

- 每槽可选、支持自定义文字，并有三个与默认值同轴、同颗粒度、同语言及表达形式的推荐项；图片是附加能力。
- Prompt 使用自然语言，每个槽位恰好出现一次。生成约束放入运行语义；开放的默认值及推荐值保持可替换，不能在固定约束中被锁回。
- 标题、描述和标签共同表达模板价值与使用动机，避免组件清单和编译术语。

文字长度与语义路由、已识别身份命名、图片输入配置、身份特征权限及标签数量，逐项执行字段规范。完成时，每个开放内容有编辑路径，每个槽位有对应 binding，固定约束有模板机制依据。

### 4. 解析 key，校验并自复核

读取 [key-registry.md](references/key-registry.md)，通过 `KeyRegistryReader.resolveTemplateKey(request)` 取得决议。文件名、目录、标题、相似度和图片 SHA 均不能代替源身份；冲突或注册表不可用只暂停当前项。

读取 [gallery-v2.md](references/gallery-v2.md)，按固定 Schema 与生产约束校验草稿。执行分析规范中的同轮 self-review：每项有具体证据，绑定最终草稿 SHA；修改后重新复核。

语义复核需实际代入不同推荐值，检查新内容能否生效、玩法是否保留、其他字段是否仍锁定旧内容。机器校验与语义判断分别完成。全部通过后，首次编译调用 `compile_final_json`，返修调用 `compile_json_revision`，不增加 JSON 人工批准停点。

### 5. 交付正式数据

每次交付读取 [portable-delivery.md](references/portable-delivery.md)。调用 `write_formal_json` 写入独立 revision 位置，再调用 `write_production_index` 更新索引。每模板目录只含一个裸 JSON；分析、自复核、注册表证据及状态置于目录外。

报告已交付 key、修订身份与索引入口。涉及工作台的任务继续执行读回分支；交付完成与工作台更新分别确认。

## 条件分支

### JSON 返修

先读取 [返修与读回校验.md](references/返修与读回校验.md)，取得当前交付、原批准图片和请求证据。修改前声明 scope，以完整上一版摘要绑定；保留未涉及的槽位、绑定和字段，随后沿主流程完成新草稿及自复核。

注册表需确认 `EXISTING_SAME_SOURCE`。上一版含氛围图字段时保持原对象只读，新产物遵循本 Skill 的字段边界。缺少可靠基线时暂停该项。用户要求换模板图时，仅将该项转回第一 Skill，取得新批准 envelope 后继续。

### 工作台读回

任务包含工作台交付时，读取 [返修与读回校验.md](references/返修与读回校验.md)。由数据台根据生产记录选择当前修订、采集实际观察，再调用 `validate_delivery_readback` 校验列表、详情、编辑预览和导出。

选版与读回均通过后才报告工作台已更新。入口不可用或内容过期时保留正式交付，标注读回待完成；较新的未交付修改继续显示待处理状态。

### 批量生产

按确定的 1–100 项分片执行，保持每项分析、key 决议、交付和错误独立。一项失败只暂停该项，其余继续；恢复使用该项记录的阶段与原因。打包和安装验证属于 Skill 维护，不进入普通模板生产流程。
