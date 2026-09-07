---
name: template-atmosphere-image-producer
description: Generate, review, upload, and register one final 3:4 lifestyle atmosphere image for each formal Memebuy template. Use for 氛围图、产品生活方式图、模板上身图, batch carrier allocation, style-card direction, print fusion, Good Case learning, OSS finalization, or top-level imageUrl backfill. Template artwork creation and template semantic JSON authoring remain with the first two production skills.
---

# Template Atmosphere Image Producer

Turn a formal template image and its Gallery JSON into one desirable product photograph. The photograph must work at first glance, the product must look physically real, and the template must remain recognizable as the printed artwork.

## Read by branch

| Task | Read |
|---|---|
| Plan or generate any atmosphere image | [business-quality-standard.md](references/business-quality-standard.md), [photographic-truth-and-color.md](references/photographic-truth-and-color.md), [creative-direction.md](references/creative-direction.md), [print-fusion.md](references/print-fusion.md) |
| Choose actors or a scene family | [topic-routing.md](references/topic-routing.md); for pet templates also read [pet-on-products.md](references/topic-profiles/pet-on-products.md) |
| Allocate a batch | [batch-allocation.md](references/batch-allocation.md) |
| Choose or maintain photography references | [style-card-system.md](references/style-card-system.md); use the local reference catalog supplied for the task |
| Create, resume, review, upload, backfill, or clean a batch | [workflow-and-artifacts.md](references/workflow-and-artifacts.md) and [review-and-finalization.md](references/review-and-finalization.md) |

## Local references

Photography references, style-card catalogs and feedback cases are private runtime inputs and are not included in this repository. Use the catalog and image paths explicitly supplied for the task. Existing local resources may remain under the ignored `assets/` directory. Read current user decisions and disabled-card records from that local source. If no usable reference is available, report the missing reference and pause generation; do not invent a bundled card or substitute a generated Good Case.

## Workflow

1. **Load formal inputs.** Bind one template key to its formal JSON and approved template artwork. Accept an absent `imageUrl`, `null`, or the current atmosphere-image URL. Existing valid URLs mean the item is already finalized unless the user requested replacement.
2. **Route the subject.** Classify the template before choosing actors. Pet, standalone-print, couple, family, fandom, character and occasion templates use different scene profiles. Add only subjects supported by the template meaning.
3. **Allocate the batch.** Maintain rolling counts for carrier, camera distance, model gender, apparel side, subject structure, style card, scene and action. Small shards may drift; the complete topic or requested batch must converge on its configured proportions.
4. **Design the product.** Choose carrier color, print treatment, placement, scale, material and visibility. Large blocks use a smaller scale or a coordinated carrier color. White exteriors are removed while internal whites remain. The result must read as ink or transfer integrated into the carrier.
5. **Direct the photograph.** Write one plausible lived event, give each visible subject an intention, and add at most one natural echo from the artwork through color, action, prop, clothing or setting. The event must still make sense when the print is mentally removed.
6. **Translate one style card.** Use one original human-provided photography card as generation reference. Preserve three to five observable traits of light, color, optics, texture and human state while changing at least three of scene topology, subject placement, action, camera geometry and set design. Generated Good Cases calibrate decisions and evaluation; they are not generation references.
7. **Generate once.** In one image-generation call, provide the formal artwork as print authority and the chosen photography card as style evidence. Produce the complete 3:4 scene with the print already integrated. A new revision starts from the formal inputs and review note. Edit a prior candidate only when the user explicitly asks to preserve that image and change a local detail.
8. **Gate and present.** Check first-glance photographic truth, clean color, anatomy, carrier physics, print identity, print scale, thumbnail visibility and batch diversity. Present reviewable candidates with stable candidate ID, template key, carrier and style-card ID. Machine checks establish eligibility; the user makes the aesthetic decision.
9. **Finalize one.** After explicit selection, upload the exact selected bytes to content-addressed Alibaba OSS, verify public readback by byte length and SHA-256, and atomically replace that template JSON's top-level `imageUrl` with the verified HTTPS URL.
10. **Prune candidates.** After JSON and workbench readback succeed, retain the selected final, receipts, decision history and compact production metadata. Delete the other candidate image files for that template. Preserve a selected Good Case as the final asset plus its Good Case metadata; do not keep a duplicate image copy.

## Invariants

- Output images are exactly 3:4.
- New production uses one-pass generation. Intermediate blank products and routine second-pass print edits are outside the default workflow.
- First-glance beauty, natural life and clean photographic color are product requirements. Obvious AI people, muddy color or a staged commercial pose are hard failures.
- Template artwork is the print authority. Text, subject identity, count, dominant markings and core composition remain recognizable.
- Printed artwork follows material folds, perspective, occlusion and surface response. Oversized, floating, badge-like or untreated rectangular prints are hard failures.
- Product and print remain legible in the target thumbnail. Environmental framing cannot make the merchandise unreadable.
- Carrier allocation defaults to T-shirt 20%, long-sleeve 20%, sweatshirt 20%, tote 20%, other carriers combined 20%.
- Among single-model images, default gender allocation is male 30% and female 70%.
- Apparel display defaults to front 80% and back 20%; artwork designed for a specific side overrides the quota.
- Camera distance defaults to close 20%, medium 50% and environmental 30%.
- Pet visibility is a topic-profile setting, normally 80%–90% for pet-led topics. Pet rules never spill into unrelated print, couple or family templates.
- The latest explicit user decision for a candidate supersedes earlier process notes. At most one candidate per template can be finalized.
- OSS mutation and candidate deletion occur only after explicit image selection. Upload readback and JSON/workbench readback must finish before local candidate pruning.

## Completion

Report the requested and actual batch distributions, candidate decisions, Good Cases, selected style cards, OSS receipts, updated JSON paths, `imageUrl` readback, pruned files and unresolved item-local failures. A template is complete only when one selected image is publicly verified, its exact URL is present in the current JSON, and its unselected candidate images are gone.
