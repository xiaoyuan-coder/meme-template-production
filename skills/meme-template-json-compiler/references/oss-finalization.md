# OSS finalization

The Memebuy production profile uses base URL `https://assets.memebuy.cn` and object key `gallery/templates/{key}/{approvedImageSha256}.png`. The key matches `^[a-z][a-z0-9-]{1,59}$`. The SHA is calculated from the exact approved PNG bytes that will be uploaded. Do not transcode after hashing.

`cover` and `referenceImage` receive the same URL: `https://assets.memebuy.cn/gallery/templates/{key}/{approvedImageSha256}.png`. Do not add batch, date, local number, revision, query, or fragment.

Create once. A persisted receipt matching key, image digest, object digest, byte length, object key, remote identity, request identity, public URL, provider-receipt digest, and upload time resumes finalization without another remote call. Otherwise an existing remote object is reusable only when object key, digest, byte length, remote identity, and request identity all match the local upload intent. After a new `put_create_once`, validate the provider response and perform a fresh `head`; both must match before creating a receipt or returning URL-filled JSON. Any mismatch is an object conflict and prohibits overwrite.

`create_aliyun_oss_adapter_from_environment` is the explicit real adapter factory. It reads `OSS_ENDPOINT`, `OSS_BUCKET_NAME`, `OSS_ACCESS_KEY_ID`, and `OSS_ACCESS_KEY_SECRET`, lazily imports `oss2`, writes SHA/length/remote/request identity metadata, and sends `x-oss-forbid-overwrite: true`. Responses retain only reconciliation facts and an optional provider request ID. Credentials and personal filesystem paths stay outside code, artifacts, and logs. Tests inject fake adapters. A JSON approval bound to the preview SHA, Approved Image SHA, reviewer, decision time, rule version, and revision is required before the first remote mutation.
