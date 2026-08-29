# Read-only key registry

Use only `KeyRegistryReader.resolveTemplateKey(request)`. The request contains `proposedKey`, optional `existingKey`, and optional `sourceIdentity={namespace, sourceAssetId, sourceSha256?}`. The response contains `registryRevision`, `decision`, `resolvedKey`, `matchedBy`, and `evidence`.

Allowed decisions are `NEW`, `EXISTING_SAME_SOURCE`, `KEY_COLLISION`, `SOURCE_CONFLICT`, and `REGISTRY_UNAVAILABLE`. Canonical source identity is `namespace + sourceAssetId`. `sourceSha256` provides integrity evidence or matches an explicitly registered legacy alias. It never replaces the canonical pair.

An `existingKey` must be confirmed by the registry. Filenames, directory numbers, batch IDs, titles, semantic similarity, and Approved Image SHA cannot establish common source. Registry unavailability or conflict pauses only that item.

Formal online resolution uses `MemeAdminKeyRegistryClient` with an explicitly supplied local base URL. It sends `POST /api/v1/template-key-registry/resolve`, JSON request/response, and no credential or write method. The endpoint returns HTTP 200 with the five-field response even for `KEY_COLLISION`, `SOURCE_CONFLICT`, or `REGISTRY_UNAVAILABLE`; malformed responses fail the current item. `SnapshotKeyRegistryReader` remains the portable/offline adapter. This repository owns the client, schemas, and seam only; meme-admin owns the read-only server implementation and registry storage.
