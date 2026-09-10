# 用户批准本地图片：直接入口

用户希望直接用给定图片制作模板 JSON，且明确批准该图时，从这里开始。批准可以来自当前对话，例如“把这张图作为已经批准的图”；保存原话及其对应文件摘要即可，无需第一 Skill 的审核包、换图记录或生图回执。仅提供图片、尚未表达批准时，先完成可独立推进的观察并确认图片用途。已给出的批准持续有效。

## 本地准入与独立分析

读取 `requirements-direct.txt`，核对依赖，缺失时报告，不自动安装。使用 `scripts/direct_input.py`：

```python
state = prepare_direct_input(
    image_path, runtime_root / "sidecars" / item_id / "direct-input.json",
    approval_evidence=user_approval_quote,
    approved_sha256=observed_image_sha256,
)
```

调用前实际查看图片并计算文件 SHA。函数验证 PNG 可解码、单帧、实际宽高与批准摘要，持久化 `approved_local` 状态和独立 UUID 源身份。相同 state 路径重跑复用原身份，字节变化时拒绝沿用旧批准。图片不被缩放、裁切或重新编码。非 PNG 图片需要单独转换并查看确认转换结果；此版本直接接收 PNG。

随后执行主流程的视觉取证、反事实、槽位设计及语义分析。分析绑定原字节 SHA。`approved_local` 表示图片批准已确认，可以分析；它尚未表示上传完成。无需等待上传配置即可完成独立分析。

`state.generationImageSize` 来自 `select_generation_image_size(width, height)`，写入正式草稿的 `imageSize`。它是生成画布；envelope 的宽高仍保存实际参考尺寸。例如 570×1002 对应生成画布 768×1344，原参考图保持 570×1002。已有支持尺寸保持原值。不要以生成画布尺寸替换参考图尺寸。

## 原图发布与 envelope

需要正式交付时，将已批准 PNG 原字节发布到本合同指定的内容寻址存储。原图发布属于直接入口的正式交付步骤，已有授权直接沿用；“仅分析、禁止上传、离线测试”的要求照常生效。维护 Skill 本身不会触发真实上传。

```python
publisher = create_publisher_from_environment()
envelope = publish_direct_input(
    image_path,
    runtime_root / "sidecars" / item_id / "direct-input.json",
    runtime_root / "sidecars" / item_id / "image-publication.json",
    publisher,
)
```

适配器读取进程环境中的 `OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`、`OSS_ENDPOINT`、`OSS_BUCKET_NAME`；凭据由运行环境注入，不进入产物、Prompt 或错误输出。使用既有目标配置，缺项时说明具体配置类别。模块提供 `prepare` 与 `publish` CLI，参数见 `--help`。

发布先按 SHA 定位对象，以禁止覆盖方式创建；已有对象核对完整字节，再通过公开 HTTPS URL 读取并逐字节比较。HTTPS 回读使用 `certifi` 提供的 CA bundle，避免运行机 Python 证书库缺失造成伪失败。只有读回成功才写 publication receipt 并返回标准 v2 `approved_uploaded` envelope。可预测的 URL 是上传意图，不能作为成功证据。失败保留本地批准与分析；重跑公开读回，复用真实存在且内容相同的对象。

发布能力内置于本 Skill 的直接入口，不调用第一 Skill、不生成新图，也不消费其他生产阶段的语义。`compile_final_json` 始终只接收经过校验的 v2 envelope；前台 `cover/referenceImage` 复用其 URL，省略 `imageUrl`。

## 独立 key 与便携数据根

选择一个跨任务稳定的 `templateDataRoot`。它是第二 Skill 的正式数据集，不需要工作台。新建模板时：

```python
decision = resolve_template_key(template_data_root, semantic_key)
```

返回 `NEW` 后调用 `compile_final_json`。正式 JSON 完成后调用 `publish_template`，以该 key 建立 revision 1、history 与 current。如果 key 已存在，新建路径返回 `KEY_COLLISION`，避免将一张新图误当成旧模板返修。

用户明确提供已有 key 时，先读取 current 并按返修流程处理。换图、改名和重构槽位都可继续使用同一 key；发布时必须提供上一版 SHA 以防止过期任务覆盖新版。直接入口 UUID 和图片 SHA 保留为来源证据。详见 [key-registry.md](key-registry.md)。

## 完成边界

两个入口最终合流到同一份 `semanticModel`、Gallery Schema、字段合同、key 决议和绑定最终草稿 SHA 的 selfReview。完成完整编译后执行 `write_formal_json`、`write_production_index` 和 `publish_template`。直接入口不会跳过玩法分析、默认为所有复核通过或产生降级正式 JSON。

缺上传配置时报告“本地批准与分析已完成，原图发布待完成”。用户未提供 `templateDataRoot` 时，请其选择稳定保存目录；该选择不要求安装或连接工作台。缺真实生成验证时明确保留该限制。只测试入口时可以运行本地准入、匿名存储适配测试及完整编译测试，测试回执只存在临时目录，不能充当用户图片的生产上传回执。
