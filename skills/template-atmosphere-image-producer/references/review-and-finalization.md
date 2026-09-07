# Review, OSS finalization, and cleanup

## Decisions

Bind every decision to candidate ID, template key, image SHA-256 and the latest user statement.

| Decision | Meaning | Next action |
|---|---|---|
| `approved` | Eligible final | Upload and backfill when selected |
| `good_case` | Approved final with reusable quality evidence | Upload, backfill and retain dimensional learning metadata |
| `revise` | Direction is useful; the note names a correction | Create a new one-pass candidate from formal inputs and the note |
| `rejected` | Current image is unusable | Create a new concept from formal inputs |
| `hold` | No decision yet | Preserve without finalizing |

A note-guided revision is a new generation. Use image editing only when the user explicitly identifies an existing image to preserve and asks for a local change.

## Finalization transaction

1. Confirm exactly one selected candidate for the template and verify its bytes still match the reviewed SHA-256.
2. Upload with a content-addressed key such as `memebuy/template-atmosphere/sha256/<sha256>.<ext>`. Use create-once semantics and record the object metadata digest.
3. Read the public HTTPS URL. Verify status, byte length and SHA-256 against the selected local image.
4. Read the current formal JSON, confirm the same template key, and require `imageUrl` to be `null`, absent only for a declared legacy migration, or the same verified URL.
5. Write a new revision atomically with only top-level `imageUrl` changed. Preserve every other value exactly.
6. Refresh the production index or personal workbench and read the current JSON through the available list/detail/export surfaces. Confirm the same URL appears for the same key.
7. Mark the finalization complete, then delete unselected candidate image files for that template. Keep JSON plans, hashes, decision history, OSS receipt and cleanup receipt. Keep the selected final in its canonical final location; a Good Case references that file instead of copying it.

Stop before cleanup whenever OSS readback, JSON write, index selection or workbench readback is incomplete. A rerun reconciles the same content-addressed object and revision identity before attempting another mutation.

## `imageUrl` ownership

The JSON Compiler creates new formal templates with top-level `imageUrl: null`. This Skill owns the transition from `null` to a verified Alibaba OSS HTTPS URL. `cover` and `referenceImage` continue to identify the reusable template artwork; `imageUrl` identifies the selected product atmosphere image.

Replacing an existing atmosphere image creates a new explicit revision. Keep the old URL in revision lineage, update the current JSON only after the new upload verifies, and prune local candidates only after the new current revision reads back successfully.
