# Generation contract

The only allowed provider operation is a FAL edit request with this exact profile:

```json
{
  "model": "openai/gpt-image-2/edit",
  "quality": "low",
  "num_images": 1,
  "output_format": "png"
}
```

`image_size` accepts exactly `1024x1024`, `1152x896`, `896x1152`, `768x1344`, or `1344x768`. The adapter submits the selected value as `{"width": W, "height": H}`. Reject `auto`, provider preset names, omitted quality, other quality values, other models, fallback models, automatic model selection, multiple images, and non-PNG output before the adapter can issue a request.

The edit payload contains exactly one source in `image_urls: [input]`; `image_url` is not part of this contract. Strategy approval binds the strategy SHA, compiled prompt SHA, source/input image SHA, portable input URI digest, rule version, revision, reviewer reference, and decision time. `submit_authorized_generation` receives that URI and the actual PNG, JPEG, or WebP bytes, recomputes their SHA, and compares both identities before the adapter seam. Only after approval, it derives an in-memory Base64 Data URI. The real adapter decodes those exact approved bytes, uploads them to FAL Storage, and sends only the resulting HTTPS URL in the generation queue payload. Neither the Data URI nor storage URL is persisted in reviews, attempt state, or logs.

One valid strategy approval authorizes one generation submit. Input hosting happens before that queue POST. A hosting failure becomes `input_hosting_failed` and may resume with the same approval because no generation request was attempted. Polling and recovery may address the same provider request. A deterministic non-retryable HTTP rejection becomes `provider_rejected`; transport failures, retryable HTTP statuses, and server failures become `submission_unknown`. Persist only the allowlisted HTTP status and provider error type, never raw response text or headers. `submission_unknown` pauses for reconciliation and never triggers a speculative resubmit.

An unknown attempt can be closed as `provider_rejected` only when a complete, bounded query of the official FAL request-history endpoint returns no request for the exact approved model window. Persist that evidence through `record_no_request_reconciliation`. This conclusion does not restore or reuse the consumed approval: any later paid request requires a new strategy revision and fresh human approval. Credentials, raw secrets, and personal paths never enter artifacts or logs.

`create_fal_adapter_from_environment` is the only bundled real-client factory. It reads `FAL_KEY`, uses `fal-client` only for hosted input storage, then sends one generation POST to `https://queue.fal.run/openai/gpt-image-2/edit` through an `httpx` client with no retry transport. Missing credential/dependency produces a safe configuration error. There is no generation fallback, automatic queue retry, or alternative model. Tests and ordinary validation inject fake adapters.
