# Gallery v2 production profile

The source-repository authority is the immutable snapshot at `contracts/upstream/gallery-template/agent-template-json-runtime-contract-2026-09-08/gallery-template.schema.json`, SHA-256 `38166c6b4939b11a1a5934fc1342baf35dba833dcda40a6179e5cde858369efb`. A standalone installation reads the byte-identical bundled copy at `references/contracts/gallery-template.schema.json`; repository tests require both digests to match.

Compile `inputSchema.version=2` and `runtimeSemantics.version=2`. Every `replace_identity` binding explicitly includes `clothingOwnership` with `source` or `template`, including one-to-one and repeated bindings. The formal object uses only the production whitelist. Upstream v1 acceptance does not authorize v1 production.

The Memebuy monorepo is an upgrade source only. Every upgrade adds a new immutable version directory, records its digest, performs a contract diff, and updates the repository release contract. Never read desktop absolute paths, `current`, or `latest` during production. Old snapshots remain migration fixtures only.

The shared snapshot permits optional `imageUrl` for downstream atmosphere delivery. The stricter second-stage whitelist excludes it entirely, both on initial compilation and revision. Only the atmosphere-image producer adds the field after human selection and OSS readback.

The reference image may have any positive pixel dimensions. `imageSize` is the generation canvas selected by `select_generation_image_size`; exact supported sizes are preserved and other sizes map to the closest supported aspect ratio. Reference bytes, SHA-256, URL and actual dimensions remain unchanged. This authoring-policy change does not alter the frozen Gallery schema or approved-image envelope v2.
