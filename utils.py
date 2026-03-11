import io, base64, numpy as np, os
from PIL import Image
from numpy.linalg import norm
import requests


def _hf_base_url() -> str:
    url = os.getenv("HF_EMBED_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("HF_EMBED_URL is not set. Deploy hf_space/ to Hugging Face and set the env var.")
    return url


def _hf_embed_url() -> str:
    return _hf_base_url() + "/embed"


def b64_to_image(b64_data: str) -> np.ndarray:
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


def image_to_b64(img: np.ndarray) -> str:
    """Convert numpy RGB array to base64 JPEG string (no data-URI prefix)."""
    pil = Image.fromarray(img.astype(np.uint8))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def image_to_embedding(img: np.ndarray) -> list:
    """Send image to HF Space and get back a Facenet512 embedding."""
    b64 = image_to_b64(img)
    try:
        resp = requests.post(
            _hf_embed_url(),
            json={"image_b64": b64},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"HF Space unreachable: {e}")
    data = resp.json()
    if not data.get("ok"):
        raise ValueError(data.get("error", "HF Space returned error"))
    return data["embedding"]


def batch_image_to_embeddings(imgs: list) -> list:
    """Send all images in a single HTTP call to HF Space /embed_batch."""
    b64_list = [image_to_b64(img) for img in imgs]
    try:
        resp = requests.post(
            _hf_base_url() + "/embed_batch",
            json={"images_b64": b64_list},
            timeout=120,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"HF Space unreachable: {e}")
    results = resp.json().get("results", [])
    embeddings = []
    for r in results:
        if r.get("ok") and r.get("embedding"):
            embeddings.append(r["embedding"])
    return embeddings


def read_image_file(file_storage) -> np.ndarray:
    img = Image.open(file_storage.stream).convert("RGB")
    return np.array(img)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return 1.0 - (np.dot(a, b) / (norm(a) * norm(b) + 1e-8))


def match_embedding(embedding: list, candidates: list, threshold: float = 0.35):
    """candidates: list of (person_doc, embedding_list)"""
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


def average_embeddings(embeddings: list) -> list:
    arr = np.array(embeddings, dtype=np.float32)
    avg = arr.mean(axis=0)
    avg = avg / (norm(avg) + 1e-8)
    return avg.tolist()

