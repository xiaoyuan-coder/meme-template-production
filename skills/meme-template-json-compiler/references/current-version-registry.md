# 便携模板数据根目录

`templateDataRoot` 是第二 Skill 自主维护的正式数据集。它跨任务、批次和日期稳定存在，不依赖工作台。任意调用方只需提供一个可持久化目录；工作台存在时作为可选读取方。

Key 是模板身份。`current-template-registry.json` 管理每个 key 当前采用的 revision；同 key 新版发布后，`current/templates/<key>.json` 原子替换，旧版保留在 history 与内容寻址对象中。

## 存储与选择

用户或调用环境显式提供 `templateDataRoot`。没有工作台时仍可完成全部流程。本仓库中临时保存个人数据时使用已忽略的 `local-data/template-data/`；不在日期批次目录中新建独立 current。

`currentRegistryRoot` 是旧 runtime envelope 字段，可作为 `templateDataRoot` 的兼容别名。它不代表工作台拥有该目录。

## 目录合同

```text
<template-data-root>/
  current-template-registry.json
  current/templates/<key>.json
  objects/<formal-sha256>.json
  history/<key>/revision-NNNN/<key>.json
```

- `current/templates/` 是对外最简单的当前版本入口。
- `objects/` 保存内容寻址正式对象。
- `history/` 保存可阅读、可回滚的历史 revision。
- 注册表每个 key 只有一条 current 记录。

## 新建与替换

编译前调用 `resolve_template_key`。完成正式 JSON 验证后调用高层接口：

```python
receipt = publish_template(
    template_data_root,
    formal,
    published_at=observed_at,
    expected_previous_formal_sha256=previous_sha_or_none,
)
```

新 key 传入 `None`，自动建立 revision 1。已有 key 必须传入编辑基线的 current SHA，函数自动继承修订链并将 revision 加一。摘要不一致时拒绝覆盖，保护较新版本。与 current 内容完全一致的重跑返回 `already_current`。

`promote_current_template` 保留为底层兼容接口；普通生产使用 `publish_template`，由模块内部维护 chain、revision、history 路径和 current 替换。

## 读取与迁移

`read_current_template_registry` 同时校验注册表、内容寻址对象、current 镜像和 history 对象。`locate_current_template` 按 key 或精确标题读取，标题重名时回到 key。

旧历史数据可用 `discover_bootstrap_candidates` 发现候选；多个不同候选由用户确认。日常生产完成后，`templateDataRoot` 已经是正式结果；工作台读回只在用户要求同步或验证工作台时执行。
