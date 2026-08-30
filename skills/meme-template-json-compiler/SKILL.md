---
name: meme-template-json-compiler
description: Compile an Approved Template Image into independently analyzed, human-reviewed Gallery v2 JSON, resolve its key through a read-only registry, and finalize its immutable OSS image URL. Use for template semantics, slots, copy, key resolution, JSON review, OSS finalization, or batch delivery.
---

# Meme Template JSON Compiler

Consume only an Approved Template Image envelope for visual semantics. The personal data workbench may supply a separate runtime envelope containing source identity for key resolution.

## Workflow

1. Confirm `jsonschema>=4.26,<5` is available before running `scripts/compiler.py`; the install-local declaration is `requirements.txt`. Report the missing dependency without installing it automatically. Validate the minimal Approved Template Image envelope with the bundled contract.
2. Read [product-model.md](references/product-model.md), then independently analyze the approved image with [approved-image-analysis.md](references/approved-image-analysis.md). Begin with `templateValue`: why the image was selected, what the reusable hook is, which mechanism stays fixed, and which facts belong only in backend semantics. Do not read source-image analysis, replacement strategy, generation prompts, provider data, or batch reasoning.
3. Read [authoring-fields.md](references/authoring-fields.md) and [gallery-v2.md](references/gallery-v2.md). Compile the smallest useful slot set, input modes, copy, tags, Prompt Template, bindings, and visual contract from the approved image. Ordinary supporting details stay fixed; dynamic groups require all five group-photo conditions.
4. Resolve the proposed key through `KeyRegistryReader.resolveTemplateKey(request)`. Read [key-registry.md](references/key-registry.md). Pause only the affected item on collision, source conflict, or registry unavailability.
5. Validate the draft against the immutable vendored Gallery snapshot and the stricter Memebuy production profile. Then perform the lightweight same-run self-review defined in the analysis reference; bind it to the final draft SHA and revise until every fixed check passes.
6. Emit the complete JSON review package, including template value and self-review evidence, to the personal data workbench and stop at `awaiting_json_approval`. A human may revise the key or draft there; every changed object requires a fresh self-review and approval.
7. After an approval bound to the preview SHA, Approved Image SHA, reviewer, decision time, rule version, and revision, read [oss-finalization.md](references/oss-finalization.md). Reuse a matching receipt before consulting OSS; otherwise upload and reconcile the exact approved PNG bytes under the content-addressed key.
8. Read [portable-delivery.md](references/portable-delivery.md). Use `write_formal_json` for create-once atomic delivery of one bare `<key>.json`, and `write_production_index` for the stable external scanner seam. Keep receipts, review history, registry evidence, and production state outside that template directory.

## Hard boundaries

- Input and runtime semantics are version 2; identity bindings explicitly declare `clothingOwnership`.
- Every slot is optional and text-capable. Image input is an additive capability using the frozen 256×256 minimum and full source option set; text+image resolves with `image_over_text`.
- Every slot has exactly three recommendations on the same semantic axis, granularity, language, and copy form as its default; clear cross-script language mismatches fail before review.
- Prompt Template contains every slot exactly once and stays user-facing. Backend generation constraints remain in runtime semantics; open defaults and recommendations never reappear as fixed visual-contract facts.
- Metadata includes 5–8 tags and at least one exact official major category.
- Key identity comes only from the registry protocol; filename, directory, batch number, title, visual similarity, and approved-image SHA cannot prove source identity.
- JSON approval precedes OSS mutation.
- No image-generation API or provider logic belongs in this Skill.
- Batch failures remain item-local.
- Repository release and install checks are maintenance actions outside ordinary JSON production.
