# Gallery v2 production profile

The source-repository authority is the immutable snapshot at `contracts/upstream/gallery-template/agent-template-json-runtime-contract-2026-08-26/gallery-template.schema.json`, SHA-256 `317ed2444a8109722fd6bdafd00c1f43b66b59096aea8b29d6aecfb2a542f608`. A standalone installation reads the byte-identical bundled copy at `references/contracts/gallery-template.schema.json`; repository tests require both digests to match.

Compile `inputSchema.version=2` and `runtimeSemantics.version=2`. Every `replace_identity` binding explicitly includes `clothingOwnership` with `source` or `template`, including one-to-one and repeated bindings. The formal object uses only the production whitelist. Upstream v1 acceptance does not authorize v1 production.

The Memebuy monorepo is an upgrade source only. Every upgrade adds a new immutable version directory, records its digest, performs a contract diff, and updates the repository release contract. Never read desktop absolute paths, `current`, or `latest` during production. Old snapshots remain migration fixtures only.
