# 模板 JSON 编译器

`meme-template-json-compiler` 将用户批准的本地图片或已上传的模板图转化为可复用的 Gallery v2 模板 JSON。它独立分析图片的玩法、主体关系和可编辑内容，建立槽位、推荐项、用户提示词与运行约束，支持首次编译、按名称或 key 定位 current、批量处理和 JSON 局部返修。

## 输入与输出

支持用户明确批准的本地 PNG 直接输入，按 [直接入口](references/direct-input.md) 记录批准、发布原图并保留来源证据；也支持 Approved Template Image v2 envelope，包含批准状态和图片的 URL、SHA-256、宽高及格式。Key 是模板身份，图片和来源身份可随 revision 变化。

输出为裸单对象 `<key>.json`，包含标题、描述、标签、Prompt Template、槽位、运行语义及模板图引用。`cover` 与 `referenceImage` 原样使用输入图片 URL。交付不包含 `imageUrl`，氛围图字段由 `template-atmosphere-image-producer` 管理。

分析证据、自复核、注册表记录和运行状态保存在正式模板目录之外。

## 使用方式

通过 `$meme-template-json-compiler` 调用，提供本地 PNG 并明确批准使用，或提供已批准图片的 envelope；局部返修同时提供上一版 JSON 和修改要求。完整工作流程见 [SKILL.md](SKILL.md)。

1. 按入口校验批准与图片，独立查看已批准图片；本地输入的发布可与分析分阶段完成。
2. 分析模板价值、玩法机制、主体关系与可编辑内容。
3. 编写槽位、文案、Prompt Template 和运行语义。
4. 解析 key，校验草稿并完成绑定草稿摘要的自复核。
5. 编译正式 JSON，写入历史交付目录并更新生产索引。
6. 调用 `publish_template` 写入稳定 `templateDataRoot`，以 key 创建或替换 current，并自动保留 history。
7. 用户要求工作台同步时，再校验实际采集的读回数据。

## 模板规则

- 槽位通常为 2–4 个；完整覆盖分析支持时可以使用单槽。
- 每个槽位可选、支持自定义文字，并提供三个同语义轴的推荐项。图片输入为附加能力。
- Prompt Template 面向用户表达可编辑内容；运行语义保持模板的玩法、构图与关系。
- `inputSchema.version` 和 `runtimeSemantics.version` 均为 2。
- key 是模板身份，由便携 `templateDataRoot` 解析和维护；批量任务按 1–100 项分片，每项独立处理失败。
- 局部返修按请求范围修改，保留未涉及的槽位、绑定和字段。

详细字段约束见 [authoring-fields.md](references/authoring-fields.md)，正式合同见 [gallery-v2.md](references/gallery-v2.md)。检索标签与视觉约束分别见 [tags.md](references/tags.md) 和 [visual-contract.md](references/visual-contract.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | Skill 执行流程 |
| [AGENTS.md](AGENTS.md) | Agent 工作约定 |
| `agents/openai.yaml` | 展示与调用元数据 |
| `scripts/compiler.py` | 编译、校验、返修与历史交付函数 |
| `scripts/current_registry.py` | 便携模板数据的 key 解析、发布、历史与 current 读取 |
| `references/` | 产品模型、分析规则、字段合同和交付规范 |
| `examples/integration-input.json` | 匿名离线示例 |
| `tests/` | 独立离线测试 |

## 规则阅读入口

按业务问题组织阅读，字段共用的判断保留在同一份规范中：

| 要解决的问题 | 规范入口 |
| --- | --- |
| 用户为什么想复用、哪些内容属于玩法 | [product-model.md](references/product-model.md) |
| 怎样从图像建立组件、身份、文字和证据 | [approved-image-analysis.md](references/approved-image-analysis.md) |
| 槽位、默认与推荐、目标绑定、前台文案怎样一起成立 | [authoring-fields.md](references/authoring-fields.md)，槽位取舍另见 [slot-decision-cases.md](references/slot-decision-cases.md) |
| 替换后如何保持媒介、画风和空间关系 | [visual-contract.md](references/visual-contract.md) |
| 哪些词能帮助用户检索模板 | [tags.md](references/tags.md) |
| 正式 JSON 接受哪些结构和值 | [gallery-v2.md](references/gallery-v2.md) 与随包 Schema |
| 怎样确定身份、历史交付与当前版本 | [key-registry.md](references/key-registry.md)、[portable-delivery.md](references/portable-delivery.md)、[current-version-registry.md](references/current-version-registry.md)、[返修与读回校验.md](references/返修与读回校验.md) |

## 运行环境

Python 3.10+，macOS 或 Linux。基础编译依赖见 `requirements.txt`，直接入口另见 `requirements-direct.txt`；文件写入需要支持硬链接的文件系统。编译器提供 Python 函数接口，图片理解由执行 Skill 的视觉 Agent 完成。

在本目录准备环境并运行离线测试：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

示例用于离线合同校验，其中的图片 URL、分析和注册表证据不作为生产数据。

## Python 接口

| 函数 | 用途 |
| --- | --- |
| `compile_final_json` | 校验分析、草稿、注册表响应及自复核，返回正式 JSON |
| `compile_json_revision` | 按声明的修改范围编译返修 JSON |
| `compile_template_revision` | 编译可换图的同 key 完整模板修订 |
| `compile_data_revision` | 不重新准入图片，按 scope 编译定向数据修订 |
| `validate_formal_json` | 校验 Schema 和生产字段约束 |
| `write_formal_json` | 写入 `<delivery_root>/<key>/<key>.json` |
| `write_production_index` | 合并生产索引 |
| `resolve_template_key` | 在便携数据根中区分新 key、已有 key 与冲突 |
| `publish_template` | 以 key 创建或替换 current，自动维护 revision 和 history |
| `promote_current_template` | 底层兼容发布接口 |
| `read_current_template_registry` | 读取并验证便携数据根的 current、history 及内容对象 |
| `locate_current_template` | 按稳定 key 或精确标题读取 current 正式 JSON |
| `discover_bootstrap_candidates` | 从明确给出的历史根目录收集并按内容去重基线候选 |
| `validate_delivery_readback` | 校验四个工作台入口的实际观察 |
| `process_batch` | 按项处理批次并隔离错误 |

先调用编译函数，再写入正式文件。同内容写入可重复执行，异内容冲突保留原文件；新修订使用独立交付位置。

key 解析见 [key-registry.md](references/key-registry.md)，返修与读回见 [返修与读回校验.md](references/返修与读回校验.md)，目录和索引约定见 [portable-delivery.md](references/portable-delivery.md)。
