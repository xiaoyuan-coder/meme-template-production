---
name: meme-template-image-producer
description: Produce a reusable meme template image from a source image through mandatory replacement, human strategy approval, one contract-locked FAL edit request, and human result approval. Use for source-image replacement planning, generation, rejection revisions, batch image production, or recovery of an existing provider request.
---

# Meme Template Image Producer

Produce only an Approved Template Image envelope. Never compile Gallery JSON, upload OSS objects, or pass source analysis to the downstream Skill.

## Workflow

1. Analyze the source image and compile a mandatory replacement strategy. A source image can never pass through unchanged.
2. Read [replacement.md](references/replacement.md) for category continuity, identity and asset groups, dependency closure, canvas, text, marks, operations, and frozen structure.
3. Read [prompt-structure.md](references/prompt-structure.md), build the complete structured prompt JSON, then use `compile_replacement_prompt`; never hand-edit the compiled prompt.
4. Emit `build_strategy_review_package` and stop at `awaiting_strategy_approval` until a human approval binds the strategy, prompt, input image URI/SHA, reviewer, decision time, rule version, and revision.
5. Before any paid request, run the deterministic preflight in `scripts/producer.py`. Read [generation-contract.md](references/generation-contract.md) for the fixed FAL contract and recovery rules.
6. Submit through `submit_authorized_generation` with a durable attempt-state mapping. Persist its `submitting` state before the adapter call. Reuse `provider_pending`; reconcile `submission_unknown` against official FAL request history; create a new strategy revision and obtain fresh approval before any new paid request.
7. Build the image review package. Read [reviews-and-revisions.md](references/reviews-and-revisions.md) for hard evidence, failure classes, and revision history.
8. Stop at `awaiting_image_approval`. Only a fresh human approval bound to the current PNG SHA, review-package SHA, reviewer, decision time, rule version, and revision may create the minimal Approved Template Image envelope.
9. For batch or external workbench integration, read [portable-batch.md](references/portable-batch.md). At every review or approved-image stop, call `write_production_index` so the external scanner sees the current revision. Isolate 1–100 items and continue unaffected items.

## Hard boundaries

- Replacement is mandatory; direct source-image delivery is outside this workflow.
- The only image API is FAL, and API submission code remains inside this Skill.
- Strategy approval precedes generation; result approval follows generation.
- A new submit always requires a new strategy revision and approval.
- The downstream envelope contains only approved image identity and portable image facts.
- Repository release and install checks are maintenance actions outside ordinary image production.
