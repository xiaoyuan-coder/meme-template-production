---
name: meme-template-json-compiler
description: Compile uploaded Approved Template Images into independently analyzed Gallery v2 JSON and deliver them directly to the template data dashboard. Use for template value analysis, high-value slot discovery, copy, key resolution, deterministic JSON compilation, batch delivery, or JSON-only revisions.
---

# Meme Template JSON Compiler

Consume only an Approved Template Image envelope for visual semantics. The personal data workbench may supply a separate runtime envelope containing source identity for key resolution.

## Workflow

1. Confirm `jsonschema>=4.26,<5` is available before running `scripts/compiler.py`; the install-local declaration is `requirements.txt`. Report the missing dependency without installing it automatically. Validate the v2 `approved_uploaded` envelope and its immutable Memebuy OSS URL with the bundled contract.
2. Read [product-model.md](references/product-model.md), then independently analyze the approved image with [approved-image-analysis.md](references/approved-image-analysis.md). Complete `templateValue` and `playDecisionModel` before inventorying components: explain why the image is fun or desirable, what version the user wants to make, which choices the user actively makes, and which mechanism keeps the result recognizable. Do not read source-image analysis, replacement strategy, generation prompts, provider data, or batch reasoning.
3. Read [authoring-fields.md](references/authoring-fields.md), [slot-decision-cases.md](references/slot-decision-cases.md), and [gallery-v2.md](references/gallery-v2.md). Run slot recall across every candidate axis, then apply the independent-choice and meaningful-variation precision gates. Compile the smallest useful executable control set, normally 2–4 high-value slots, plus input modes, copy, tags, Prompt Template, bindings, and visual contract. One slot is valid when the complete coverage review finds one core control; more than four slots fail before review. Group visible text by semantic unit before routing its regions. When one human intent spans visual and text targets that the backend cannot bind to one input, keep separate slots and describe their semantic relationship without claiming automatic synchronization.
4. Resolve the proposed key through `KeyRegistryReader.resolveTemplateKey(request)`. Read [key-registry.md](references/key-registry.md). Pause only the affected item on collision, source conflict, or registry unavailability.
5. Validate the draft against the immutable vendored Gallery snapshot and the stricter Memebuy production profile. Then perform the lightweight same-run self-review defined in the analysis reference; every check carries concrete evidence references, binds to the final draft SHA, and is rerun after any change.
6. Call `compile_final_json`. It validates the analysis, key decision, Gallery profile, self-review freshness, and copies the upstream image URI unchanged into both `cover` and `referenceImage`. There is no JSON approval pause.
7. Read [portable-delivery.md](references/portable-delivery.md). Use `write_formal_json` for create-once atomic delivery of one bare `<key>.json`, then update `write_production_index`. When the template data dashboard is part of the task, register or reuse its real scan root and read back the delivered revision, source image, template image, and item count before reporting dashboard visibility. Keep analysis evidence, registry evidence, and production state outside the template directory.
8. For JSON-only revisions, reuse the same Approved Template Image envelope and recompile directly. If the image changes, return that item to the Image Producer’s second approval point; the new approved PNG receives a new immutable URL before compilation resumes.

## Hard boundaries

- Input and runtime semantics are version 2; identity bindings explicitly declare `clothingOwnership`.
- Every slot is optional and text-capable. Image input is an additive capability using the frozen 256×256 minimum and full source option set; text+image resolves with `image_over_text`.
- Every slot has exactly three recommendations on the same semantic axis, granularity, language, and copy form as its default; clear cross-script language mismatches fail before review.
- Production templates target 2–4 high-value slots. Slot count is the result of core user decisions: one slot requires a complete all-axis coverage review, and more than four slots are rejected.
- Every selected slot maps to exactly one executable control decision and passes user motivation, independent choice, meaningful variation, visibility, model control, and mechanism-preservation gates. Several control decisions may serve one higher-level user intent when the backend exposes separate bindings.
- Text regions that form one sentence, joke, comparison, or label system share one semantic unit and one slot; spatial separation alone never creates another control.
- Quick text slots stay short: CJK-like text uses at most 20 characters; whitespace-delimited copy uses at most 7 tokens and 48 total characters. Longer supporting copy routes to `free_editable` or remains fixed.
- A recognizable IP, real person, or historical figure uses the specific conventional name as the identity default. Appearance-only wording is valid only when the identity is genuinely unresolved.
- Prompt Template contains every slot exactly once and stays user-facing. Backend generation constraints remain in runtime semantics; open defaults and recommendations never reappear as fixed visual-contract facts.
- Metadata includes 5–8 tags and at least one exact official major category.
- Key identity comes only from the registry protocol; filename, directory, batch number, title, visual similarity, and approved-image SHA cannot prove source identity.
- `cover` and `referenceImage` exactly reuse the immutable URL received from the Image Producer.
- This Skill has no OSS client, upload credential, PNG input, image approval, or JSON approval state.
- No image-generation API or provider logic belongs in this Skill.
- Production jobs may contain hundreds of items; callers use deterministic 1–100 item shards and keep failures item-local.
- Repository release and install checks are maintenance actions outside ordinary JSON production.
