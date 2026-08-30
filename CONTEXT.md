# Meme Template Production

This context turns an approved image into a reusable in-app template whose editable request and generated result remain recognizably faithful to the template mechanism.

## Language

**Template**:
An in-app reusable image experience made of an approved template image, a user-facing Prompt Template, structured slots, and backend visual semantics.
_Avoid_: Prompt, reference image

**Template Mechanism**:
The stable action, relationship, layout, container, or visual joke that makes a template worth reusing after user inputs change.
_Avoid_: Style alone, subject count

**Slot**:
A high-value editable concept with text input as its base capability and optional image input when a user-owned image can map clearly to the target.
_Avoid_: Image-only slot, every visible object

**Slot Mode**:
The interaction in which a user changes a Slot through custom text, recommendations, or an available image input.
_Avoid_: Form mode

**Free-edit Mode**:
The interaction in which a user edits the full Prompt Template while the Template Mechanism remains enforced by backend semantics.
_Avoid_: Unconstrained generation

**Identity Unit**:
One user-controlled identity that may appear in one or more target instances.
_Avoid_: Every visible person, visual group

**Addressable Pair**:
Two distinct Identity Units with fixed or independently controllable roles, even when the reference image presents them as one photo.
_Avoid_: Dynamic group

**Repeated Identity**:
One Identity Unit rendered into multiple target instances.
_Avoid_: Multiple independent subjects

**Dynamic Identity Group**:
A variable-size, same-kind group whose whole-group identity is supplied and preserved as one user input, with no independently addressable member roles.
_Avoid_: Any multi-subject image, fixed pair, fixed-position collection

**Fixed-layout Collection**:
Multiple entities distributed across template-defined positions and controlled as one textual content concept, such as twelve animals occupying twelve clock positions.
_Avoid_: Dynamic Identity Group

**Image Capability**:
An optional Slot capability used when the uploaded visual source has a natural, unambiguous mapping to its target.
_Avoid_: Slot type

**Visual Contract**:
Backend-only constraints that preserve the Template Mechanism, medium, composition, relations, and rendering behavior across both interaction modes.
_Avoid_: User-facing Prompt Template

**Discovery Copy**:
The user-facing title and description that make a Template understandable and appealing before use.
_Avoid_: Analysis summary, implementation instruction

**Search Tag**:
A concise user-query term that helps retrieve a Template by its stable mechanism, emotion, scene, use case, subject class, or medium.
_Avoid_: Visual inventory, open default value, batch-generic filler

**Feature Authority Decision**:
A per-identity decision that assigns each visible trait to the uploaded identity or the Template Mechanism, with the template retaining only the smallest mechanism-critical exceptions.
_Avoid_: Copy all source-image traits, freeze the whole template subject

**Replacement Feature Authority**:
A first-stage per-component decision that separates the pixels which must be redrawn from the visible design allowed to change. Target-owned features carry the new identity, template-owned features preserve the source mechanism, and derived features only reconcile contact, lighting, or cleanup.
_Avoid_: Treat the dependency closure as permission for the new identity to redesign every covered component

**Free-editable Content**:
Meaningful picture content kept as natural literal wording in the Prompt Template so it can be changed in Free-edit Mode without becoming a Slot.
_Avoid_: Hidden constraint, omitted content

**Locked Visual Text**:
Visible text whose exact content belongs to the Template Mechanism, environment, or layout and remains fixed through backend semantics.
_Avoid_: Forgotten editable text, watermark
