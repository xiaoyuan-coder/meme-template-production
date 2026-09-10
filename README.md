# 模板生产 Skills

本仓库提供三个可独立使用的 Skill，覆盖模板图生产、模板 JSON 编译与氛围图生产。

| Skill | 功能 | 使用入口 |
| --- | --- | --- |
| meme-template-image-producer | 来源图片经过替换、审核与上传，产出已批准模板图 | [SKILL.md](skills/meme-template-image-producer/SKILL.md) |
| meme-template-json-compiler | 独立分析已批准图片，编译可复用的 Gallery v2 模板 JSON | [README.md](skills/meme-template-json-compiler/README.md) |
| template-atmosphere-image-producer | 根据正式模板生成产品生活方式图，审核后上传并回填氛围图地址 | [SKILL.md](skills/template-atmosphere-image-producer/SKILL.md) |

第二 Skill 的首次与返修交付均省略 `imageUrl`，该字段由第三 Skill 添加。`cover` 与 `referenceImage` 使用已批准模板图地址。第二 Skill 以 key 为模板身份，在独立便携 `templateDataRoot` 中维护 history 和 current；工作台为可选读取方。

本地正式数据不进入源码版本库。第二 Skill 使用跨运行稳定的便携 `templateDataRoot`；需要放在本仓库时统一置于被忽略的 `local-data/`。批次过程数据继续置于被忽略的 `runs/` 和 `outputs/`。

## 使用

下载仓库后，选择 `skills/` 下所需的完整 Skill 文件夹。每个 Skill 自带运行所需的指令、参考规范、脚本与合同；依赖以各自 `requirements.txt` 为准。

## 仓库结构

- `skills/`：Skill 指令、参考资料、执行脚本与独立测试。
- `contracts/`：共享合同、固定版本 Schema、current 注册表合同与规则实现映射。
- `tests/`：合同、编译、文件写入及安装验证。
- `scripts/`：仓库维护工具。
- `CONTEXT.md`：业务领域术语。
- `release.json`：版本与 Schema 引用。

## 验证

在仓库根目录执行：

```bash
python3 -m venv .venv-validation
source .venv-validation/bin/activate
python3 -m pip install -r requirements.txt
PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s skills/meme-template-json-compiler/tests -p 'test_*.py' -v
```

默认测试使用匿名 fixture 和本地临时目录，不调用真实生图或 OSS 上传。真实图像效果与工作台连接需在实际运行环境中验证。

维护打包工具要求正式构建来自干净的已提交版本；普通 Skill 使用无需执行打包或安装验证。
