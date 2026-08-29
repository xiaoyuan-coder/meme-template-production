# Gallery 字段编写方法

## key

从核心机制、动作、关系、容器或稳定视觉钩子生成小写 kebab-case 候选。去掉默认身份、开放文字、素材号、目录号、批次、日期、revision 和随机串。候选 key 只能通过 KeyRegistryReader 获得运行决议。

## title 与 description

title 使用用户能直接理解的稳定机制名。四门禁全部通过：图像有根据、有用户使用动机、口语自然、全部开放槽换成最大差异合法值后仍成立。具体 IP、姓名、年龄、性别、物种、发型、服装、颜色和默认文字只在它们保持固定时才能进入稳定骨架。description 补充使用场景，1–20 字，优先清晰合法。

## metadata.tags

逐图生成 5–8 项，每项 1–12 字，不重复。每个 tag 记录 `visualEvidence` 和稳定分类 `mechanism/subject/scene/medium/emotion/use_case/text/relation`。至少一项来自机制、主体、场景或媒介大类。批量不复制通用 tag 组。

## imageSize

精确读取 Approved Image 宽高，必须等于五个正式尺寸之一。

## 槽位、默认值和推荐

先穷尽高价值候选，再确定 2–5 个槽位，常态约 3 个。单槽需保存对主体、文字、物件、服装、颜色、道具、场景和嵌套内容的穷尽证据。每个候选同时通过用户动机、结果可见、模型可控、机制保持四门禁。低价值装饰和轻微渲染参数不用来补数。

ID 使用稳定英文角色/位置名，不写当前默认身份。默认值来自当前图，中文优先 2–8 字，原则上不超过 12 字；精确画字例外绑定图片 SHA 和文字区。文字模式恰好 3 个同轴、同颗粒度、非重复且适配姿态/容器/接触/媒介的推荐。纯图片动态群组不生成文字推荐。

## 主体、身份绑定与服装归属

固定可寻址主体使用独立 subject 和 `one_to_one`。同一身份的多个实例使用 `same_source_repeated`。动态群组只在“整组身份保真、合照是自然输入、人数可变、成员同类、无必须单独寻址角色”五项全部成立时使用 `preserve_group`。固定 CP、家庭角色位、人宠混合和固定人数不使用动态群组。

身份图只接管身份目标，背景和无关道具不进入模板。内容图是绑定内容的唯一题材源。每个 subject 独立裁决身份、肤/毛色、发型、服装、配饰、表情和动作的继承/固定范围，两个列表互斥。每个 `replace_identity` binding 显式写 `clothingOwnership=source|template`。

## Prompt Template

使用 1–3 句用户可读自然语言，完整描述画面，覆盖所有槽位和 `free_editable` 内容。语气直接，通常保持约 50–180 字的柔性范围。不出现 `runtimeSemantics/visualContract/inputBindings/targetInstances/clothingOwnership`、内部 ID、治理说明、制作脚手架或用强约束锁回开放默认值。

## runtimeSemantics.visualContract 与 inputBindings

`inputBindings` 精确描述用户输入接管哪个目标。`visualContract` 用正向可观察语句保留媒介、风格特征、构图、关系、色彩和光线，覆盖全部组件并区分统一媒介与有意混合媒介。可借鉴 OpenAI 生图提示原则保持清晰、具体、结构化，Gallery 字段与版本不改变。每个开放值只有一个动态事实源，固定视觉层不恢复用户已改写内容。

## cover 与 referenceImage

两字段只由 OSS 意图投影，精确相等。分析阶段的独立方法是确认它们都引用当前 Approved Image，并记录该图 SHA 与尺寸；具体 URL 由冻结 key 和实际 PNG 字节 SHA 确定。
