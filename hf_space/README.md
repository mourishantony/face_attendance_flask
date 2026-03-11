---
title: Face Embedding API
emoji: 🎯
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# Face Embedding API

FastAPI service that accepts a base64-encoded face image and returns a **Facenet512** embedding vector (512 floats).

## Endpoint

`POST /embed`

```json
{ "image_b64": "<base64 string or data URI>" }
```

Response:
```json
{ "ok": true, "embedding": [0.12, -0.34, ...] }
```

`GET /health` — liveness check.
