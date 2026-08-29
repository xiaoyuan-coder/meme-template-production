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

The edit payload contains exactly one source in `image_urls: [input]`; `image_url` is not part of this contract. Strategy approval binds the strategy SHA, compiled prompt SHA, source/input image SHA, portable input URI digest, rule version, revision, reviewer reference, and decision time. `submit_authorized_generation` receives that URI and the actual PNG, JPEG, or WebP bytes, recomputes their SHA, and compares both identities before the adapter seam. Only after approval, it derives an in-memory Base64 Data URI for the provider payload. This avoids a separate pre-approval storage upload; the Data URI is never persisted in reviews, attempt state, or logs.

One valid strategy approval authorizes one submit. Polling and recovery may address the same provider request. `submission_unknown` pauses for reconciliation and never triggers a speculative resubmit. Credentials, raw secrets, and personal paths never enter artifacts or logs.

`create_fal_adapter_from_environment` is the only bundled real-client factory. It reads `FAL_KEY`, lazily imports `fal_client`, and submits once through the exact approved model. Missing credential/dependency produces a safe configuration error. There is no fallback, automatic retry, or alternative model. Tests and ordinary validation inject fake adapters.
