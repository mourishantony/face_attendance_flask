import os

class Config:
    SECRET_KEY      = os.getenv("SECRET_KEY", "dev-secret")
    ADMIN_PIN       = os.getenv("ADMIN_PIN", "1827")
    MONGODB_URI     = os.getenv("MONGODB_URI", "mongodb://localhost:27017/attendance")
    MONGODB_DB      = os.getenv("MONGODB_DB", "attendance")
    # HF Space public URL — set after deploying hf_space/
    HF_EMBED_URL    = os.getenv("HF_EMBED_URL", "")
    # Fallback defaults (overridden by settings stored in MongoDB)
    TIMEZONE        = os.getenv("TIMEZONE", "Asia/Kolkata")
    ATTEND_START    = os.getenv("ATTEND_START", "00:00")
    ATTEND_END      = os.getenv("ATTEND_END", "21:00")

