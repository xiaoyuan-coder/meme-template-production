# 换图 Prompt 结构

先产生 `promptSections` JSON，再交给 `compile_replacement_prompt`。结构中只有以下 12 段，每段出现一次：

1. `task`：基于参考图完成整图编辑，输出独立模板图。
2. `target`：旧目标的位置、范围和新目标。
3. `dependencyClosure`：重复实例、派生内容、身份文字和接触边界。
4. `identityGroups`：逐组成员、关系和一对一新身份。
5. `featureAuthority`：逐项说明哪些可见设计由新身份接管、哪些由模板机制保持、哪些只作派生一致性重绘。
6. `canvas`：画布路由、目标区、排除区和正视化/裁框动作。
7. `markPolicy`：每个水印、商标、贴纸、装饰图标和身份标的动作。
8. `frozenSet`：需保持的机制、构图、关系、文字、语言和非目标视觉锚点。
9. `visualFeatures`：媒介、构图、比例、色光、表面和钩子；有人脸时写出可观察的脸型、眼形、嘴型和表情语法。
10. `residualCleanup`：清除被 `target_identity` 接管的旧身份特征和未授权残留，同时保留 `template_mechanism` 的设计。
11. `spatialRelations`：接触、遮挡、持握、穿戴、容器内外、前后层级和顺序。
12. `output`：单图、PNG、已选画布、完整画布和清晰度。

段落使用简洁可执行的正向语句。一条规则只写一次，对应细节聚合成短列表。人工审核绑定整个策略对象的 SHA。任何段落、替换值、画布、尺寸或规则版本变化都生成新 revision 和新审批。
