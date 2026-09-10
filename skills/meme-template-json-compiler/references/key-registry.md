# Key 身份与解析

Key 是模板的稳定身份。标题、图片、槽位、Prompt 和其他正式字段可随 revision 变化；同一 key 的新版本替换 current，key 保持不变。`sourceIdentity` 和图片 SHA 是来源与完整性证据，不承担模板身份判定。

## 便携解析

读取 [current-version-registry.md](current-version-registry.md) 指定的稳定 `templateDataRoot`，调用 `scripts/current_registry.py` 的：

```python
decision = resolve_template_key(
    template_data_root,
    proposed_key,
    existing_key=existing_key_or_none,
)
```

- 新建时不传 `existing_key`。key 未被占用返回 `NEW`；已存在返回 `KEY_COLLISION`，不默认覆盖。
- 返修或换图时显式传入同一 `existing_key`。它存在且与 `proposed_key` 一致时返回 `EXISTING_KEY`。
- `KEY_CONFLICT` 表示用户指定的旧 key 不存在或与草稿 key 不一致。

文件名、目录号、批次、标题、图片 URL 和 SHA 均不代替 key。只给标题时先在 current 中精确查找；标题重名时由用户选择 key。

## 可选外部适配

`MemeAdminKeyRegistryClient` 与 `SnapshotKeyRegistryReader` 保留为旧数据迁移或外部目录查询适配器。它们不是生产前置条件，也不得覆盖 `templateDataRoot` 内以 key 为身份的 current 事实。旧决议 `EXISTING_SAME_SOURCE` 仅用于兼容已有适配器。
