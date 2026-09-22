# 固定 Badcase 回归门禁

回归样本是只读测量基准。评测过程不修复样本、不替换期望值、不把已知错误改成通过版。Skill 或门禁调整后，对同一份输入重新编译，用新输出与固定回归合同比较。

## 每个 case 的显式期望

- `expectedSlotIds`：完整且有序的槽位集合；缺少围绕装饰等高价值控制时失败。
- `completeObjectSlots`：声明槽位可控的完整对象词。默认值和三个推荐项都必须含对象词，例如“蓝色粗边爱心”，不接受只有“蓝色粗边”。
- `editableFacts`：声明 Prompt 或槽位拥有的开放事实、Visual Contract 禁止残留的旧值，以及必须闭合的全部 target。
- `tagging`：保留图片打标器的 `hiddenTags` 和 `keywords`，门禁重新合并后与 `metadata.tags` 按顺序精确比对。

case 缺失、槽位集合不等、完整对象被拆成修饰词、开放事实被 Visual Contract 写死、联动 target 不全或 tag 合并漂移，均使回归失败。

完整编译同时执行作者门禁：`visual_attribute` 只接受有固定载体证据的文字型颜色、材质或图案控制；每个槽位的默认值与三个推荐项都必须进入 Runtime 禁写词；普通颜色背景、局部描边和默认双色组合不得进入 tags。回归套件负责固定样本期望，作者门禁负责拦截同类新数据。

## 运行

```bash
python scripts/evaluate_regressions.py --dataset <new-output.json> --suite <fixed-suite.json>
```

dataset 支持模板数组，或包含 `templates` 数组的对象。退出码 `0` 表示全部通过，`1` 表示发现回归，`2` 表示输入合同错误。
