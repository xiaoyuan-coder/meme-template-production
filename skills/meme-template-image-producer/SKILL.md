---
name: meme-template-image-producer
description: Produce and upload reusable meme template images in batches through mandatory replacement, two compact Codex-chat approvals, one contract-locked FAL edit per item, and content-addressed OSS finalization. Use for replacement planning, image generation, batch review, image approval, OSS delivery, revisions, or provider recovery.
---

# Meme Template Image Producer

Produce an Approved Template Image envelope whose image URI is already an immutable OSS URL. Never compile Gallery JSON or pass source analysis to the downstream Skill.

## Workflow

1. Analyze the source image and compile a mandatory replacement strategy. A source image can never pass through unchanged.
2. Read [replacement.md](references/replacement.md) for category continuity, identity and asset groups, dependency closure, canvas, text, marks, operations, and frozen structure. For the complete production job, collect every compatible replacement fingerprint first, run `build_replacement_diversity_report`, and use its allocations before compiling any item strategy. A recognizable anime candidate uses a franchise-and-character fingerprint.
3. Read [prompt-structure.md](references/prompt-structure.md), build the complete structured prompt JSON, then use `compile_replacement_prompt`; never hand-edit the compiled prompt.
4. Use `plan_production_job` to split a large job into deterministic 1–100 item execution shards; the default is 50. Build each item package, then emit one compact replacement table with `build_batch_strategy_chat_review`. Pause in the Codex conversation at `awaiting_strategy_approval`. The human may approve all rows or exclude item IDs. Persist item-level approvals bound to each strategy, prompt, input image URI/SHA, reviewer, decision time, rule version, and revision.
5. Before any paid request, run the deterministic preflight in `scripts/producer.py`. Read [generation-contract.md](references/generation-contract.md) for the fixed FAL contract and recovery rules.
6. Submit through `submit_authorized_generation` with a durable attempt-state mapping. Persist its `submitting` state before the adapter call. Reuse `provider_pending`; reconcile `submission_unknown` against official FAL request history; create a new strategy revision and obtain fresh approval before any new paid request.
7. After provider results are saved as valid PNGs, build item image-review packages and one before/after thumbnail sheet with `build_batch_image_chat_review`. Read [reviews-and-revisions.md](references/reviews-and-revisions.md). Pause in the Codex conversation at `awaiting_image_approval`; the human may approve all rows or exclude item IDs.
8. For every approved row, call `finalize_approved_template_image`. It verifies the fresh image approval, uploads the exact PNG bytes create-once to `gallery/template-images/<sha256>.png`, reconciles OSS metadata, and emits the v2 `approved_uploaded` envelope. The OSS URL is the image URI passed to the JSON Compiler.
9. Read [portable-batch.md](references/portable-batch.md). Persist job-level diversity, shard state, review manifests, receipts, and item state outside delivery artifacts. Call `write_production_index` at every pause or completion seam. A failed item resumes locally; unaffected items and shards continue.

## Hard boundaries

- Replacement is mandatory; direct source-image delivery is outside this workflow.
- The only image API is FAL, and API submission code remains inside this Skill.
- Strategy approval precedes generation; result approval follows generation; both approvals appear in the Codex conversation.
- A new submit always requires a new strategy revision and approval.
- Batch-compatible replacement alternatives are allocated across the complete job before per-item strategy authoring; avoidable character concentration is repaired before the strategy table is shown.
- Image approval immediately authorizes the exact PNG upload. Changing pixels creates a new SHA, a new image review, and a new OSS object.
- JSON-only changes reuse the existing Approved Template Image envelope and incur no OSS call.
- The downstream envelope contains only approved image identity, immutable OSS URL, dimensions, and MIME.
- Repository release and install checks are maintenance actions outside ordinary image production.
