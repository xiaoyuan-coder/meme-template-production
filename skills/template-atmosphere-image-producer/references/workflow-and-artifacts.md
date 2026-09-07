# Batch workflow and artifacts

Keep reusable rules and reference assets in the Skill. Put every production run in a user-selected batch directory:

```text
<batch-dir>/
├── batch.json
├── allocation.json
├── plans/
├── candidates/
├── references/
├── receipts/
├── reports/
└── decisions.json
```

Initialize and resume with `scripts/atmosphere_workflow.py`. Existing batches are create-once and resume from disk state.

Allocate the complete batch before writing per-image plans. The input is a JSON array of `{templateKey, topicRoute, singleModel}` objects:

```bash
python3 scripts/allocate_batch.py \
  --input <templates.json> \
  --output <batch-dir>/allocation.json \
  --pet-visibility 0.85
```

The allocator uses largest-remainder rounding and stable key-based ordering for carrier, camera distance, eligible single-model gender, apparel side and pet visibility. Copy each assignment into its plan, then record any semantic override and the resulting drift.

## Plan contract 2.0

Each plan binds:

- candidate ID, template key, formal JSON and formal artwork;
- topic route and optional topic profile;
- carrier, carrier color, print side, treatment, scale, placement and material;
- actor structure, single-model gender when applicable, lived event and one semantic echo;
- camera distance, scene family and one original photography style card;
- style fingerprint plus at least three deliberate scene variations;
- one `generationPrompt` and `generationStrategy.mode: one_pass`;
- post-generation hard-gate observations.

Pet fields are required only for pet routes. Couple and family routes record each person's independent action and the shared causal link. Standalone-print routes record why no pet is present.

Validate before generation and again before candidate registration:

```bash
python3 scripts/atmosphere_workflow.py validate-plan --plan <plan.json>
python3 scripts/atmosphere_workflow.py add-candidate \
  --batch-dir <batch-dir> \
  --candidate-json <candidate.json>
```

The candidate binds source image, formal artwork, style reference and final candidate paths by SHA-256. Generate and bind one candidate at a time; never infer ownership from file modification time.

## Review

Record the latest explicit decision by stable candidate ID:

```bash
python3 scripts/atmosphere_workflow.py decide \
  --batch-dir <batch-dir> \
  --candidate-id <candidate-id> \
  --decision approved \
  --reason <review-evidence>
```

Supported decisions are `approved`, `good_case`, `revise`, `hold` and `rejected`. A Good Case is also eligible for final selection.

## Finalization

Use `scripts/finalize_atmosphere.py` in three explicit stages:

1. `upload` creates or reconciles the content-addressed OSS object and writes a verified receipt.
2. `backfill` writes a new formal JSON revision with only top-level `imageUrl` changed.
3. `prune` verifies the receipt and current JSON, retains the selected image, and deletes other candidate image files for that template.

The caller refreshes the production index or personal workbench between backfill and prune, then supplies the read-back JSON to `prune`. If the workbench cannot be read, finalization remains pending and candidate files stay in place.

## Recovery

- An interrupted upload reconciles the same content-addressed key.
- A conflicting existing OSS object stops the item.
- A conflicting JSON output stops the item and preserves both source and receipt.
- A stale candidate SHA returns the item to review.
- Pruning is idempotent and records retained, deleted and already-missing files.
- One failed item does not block unrelated templates in the batch.
