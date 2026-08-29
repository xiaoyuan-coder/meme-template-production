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
