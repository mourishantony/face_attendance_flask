"""
Hugging Face Spaces — Face Embedding Inference Service
Accepts a base64-encoded image, returns a Facenet512 embedding vector.
Deploy this folder as a Gradio/FastAPI Space (SDK: docker or gradio).
"""
import io, base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
from PIL import Image
from deepface import DeepFace

app = FastAPI(title="Face Embedding API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

EMBED_MODEL = dict(model_name="Facenet512", detector_backend="opencv")


class EmbedRequest(BaseModel):
    image_b64: str  # may include data URI prefix


class EmbedResponse(BaseModel):
    ok: bool
    embedding: list[float] | None = None
    error: str | None = None


class BatchEmbedRequest(BaseModel):
    images_b64: list[str]


class BatchEmbedResponse(BaseModel):
    results: list[EmbedResponse]


def b64_to_array(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return np.array(img)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    try:
        img_arr = b64_to_array(req.image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image decode error: {e}")

    try:
        rep = DeepFace.represent(img_path=img_arr, enforce_detection=True, **EMBED_MODEL)
        if isinstance(rep, list):
            emb = rep[0]["embedding"] if isinstance(rep[0], dict) else rep[0]
        elif isinstance(rep, dict):
            emb = rep["embedding"]
        else:
            raise RuntimeError("Unexpected format")
        return EmbedResponse(ok=True, embedding=list(map(float, emb)))
    except Exception as e:
        return EmbedResponse(ok=False, error=str(e))


def _embed_one(b64: str) -> EmbedResponse:
    try:
        img_arr = b64_to_array(b64)
    except Exception as e:
        return EmbedResponse(ok=False, error=f"Image decode error: {e}")
    try:
        rep = DeepFace.represent(img_path=img_arr, enforce_detection=True, **EMBED_MODEL)
        if isinstance(rep, list):
            emb = rep[0]["embedding"] if isinstance(rep[0], dict) else rep[0]
        elif isinstance(rep, dict):
            emb = rep["embedding"]
        else:
            raise RuntimeError("Unexpected format")
        return EmbedResponse(ok=True, embedding=list(map(float, emb)))
    except Exception as e:
        return EmbedResponse(ok=False, error=str(e))


@app.post("/embed_batch", response_model=BatchEmbedResponse)
def embed_batch(req: BatchEmbedRequest):
    return BatchEmbedResponse(results=[_embed_one(b64) for b64 in req.images_b64])
