import io, base64, numpy as np, json, os
from PIL import Image
from deepface import DeepFace
from numpy.linalg import norm

EMBED_MODEL = dict(model_name="Facenet512", detector_backend="opencv")

def b64_to_image(b64_data: str) -> np.ndarray:
    # b64_data may include "data:image/jpeg;base64," prefix
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)

def image_to_embedding(img: np.ndarray) -> list:
    rep = DeepFace.represent(img_path = img, enforce_detection=True, **EMBED_MODEL)
    # DeepFace.represent returns list when passing raw array; ensure vector only
    if isinstance(rep, list):
        # may be list of dicts
        if len(rep) and isinstance(rep[0], dict) and "embedding" in rep[0]:
            emb = rep[0]["embedding"]
        else:
            emb = rep[0]
    elif isinstance(rep, dict) and "embedding" in rep:
        emb = rep["embedding"]
    else:
        raise RuntimeError("Unexpected embedding format")
    return list(map(float, emb))

def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return 1.0 - (np.dot(a, b) / (norm(a) * norm(b) + 1e-8))

def match_embedding(embedding: list, candidates: list, threshold: float = 0.35):
    # candidates: list of (person, embedding list)
    best = None
    best_dist = 999.0
    for person, emb in candidates:
        d = cosine_distance(embedding, emb)
        if d < best_dist:
            best_dist = d
            best = person
    if best is not None and best_dist <= threshold:
        return best, float(best_dist)
    return None, float(best_dist)

def read_image_file(file_storage) -> np.ndarray:
    img = Image.open(file_storage.stream).convert("RGB")
    return np.array(img)

def serialize_embedding(vec: list) -> str:
    return json.dumps(vec)

def deserialize_embedding(text: str) -> list:
    return json.loads(text)
