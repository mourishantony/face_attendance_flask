from datetime import datetime, date
from pymongo import MongoClient, ASCENDING
from bson import ObjectId
import os

_client: MongoClient | None = None
_db = None


def init_db(app):
    """Call once at app startup with the Flask app instance."""
    global _client, _db
    _client = MongoClient(app.config["MONGODB_URI"])
    _db = _client[app.config["MONGODB_DB"]]
    # Indexes
    _db.people.create_index([("name", ASCENDING)], unique=True)
    _db.attendance.create_index([("person_id", ASCENDING), ("date", ASCENDING)])
    return _db


def get_db():
    return _db


# ─────────────────────────────────────────────
# People helpers
# ─────────────────────────────────────────────

def person_create(name: str, role: str, class_name: str | None, embedding: list) -> str:
    doc = {
        "name": name,
        "role": role,
        "class_name": class_name,
        "embedding": embedding,            # stored as native array
        "registered_at": datetime.utcnow(),
    }
    result = get_db().people.insert_one(doc)
    return str(result.inserted_id)


def person_find_by_name(name: str):
    return get_db().people.find_one({"name": name})


def person_find_by_id(pid: str):
    return get_db().people.find_one({"_id": ObjectId(pid)})


def person_all():
    return list(get_db().people.find().sort([("role", -1), ("class_name", 1), ("name", 1)]))


def person_distinct_classes():
    return [c for c in get_db().people.distinct("class_name") if c]


# ─────────────────────────────────────────────
# Attendance helpers
# ─────────────────────────────────────────────

def attendance_mark_present(person_id: str, dt: date, timestamp: datetime):
    """Insert a present record only if one doesn't already exist for today."""
    db = get_db()
    date_str = dt.isoformat()
    existing = db.attendance.find_one({"person_id": person_id, "date": date_str, "status": "present"})
    if not existing:
        db.attendance.insert_one({
            "person_id": person_id,
            "date": date_str,
            "timestamp": timestamp,
            "status": "present",
            "source": "kiosk",
        })
        return True
    return False


def attendance_mark_absent(person_id: str, dt: date, timestamp: datetime):
    db = get_db()
    date_str = dt.isoformat()
    present  = db.attendance.find_one({"person_id": person_id, "date": date_str, "status": "present"})
    absent   = db.attendance.find_one({"person_id": person_id, "date": date_str, "status": "absent"})
    if not present and not absent:
        db.attendance.insert_one({
            "person_id": person_id,
            "date": date_str,
            "timestamp": timestamp,
            "status": "absent",
            "source": "scheduler",
        })


def attendance_for_person_date(person_id: str, dt: date, status: str = "present"):
    """Return list of records sorted by timestamp asc."""
    return list(
        get_db().attendance.find(
            {"person_id": person_id, "date": dt.isoformat(), "status": status}
        ).sort("timestamp", 1)
    )


# ─────────────────────────────────────────────
# Settings helpers (attendance window, timezone)
# ─────────────────────────────────────────────

_SETTINGS_ID = "global"


def settings_get(defaults: dict) -> dict:
    db = get_db()
    doc = db.settings.find_one({"_id": _SETTINGS_ID})
    if doc is None:
        return defaults.copy()
    return {
        "TIMEZONE":     doc.get("timezone",     defaults["TIMEZONE"]),
        "ATTEND_START": doc.get("attend_start", defaults["ATTEND_START"]),
        "ATTEND_END":   doc.get("attend_end",   defaults["ATTEND_END"]),
    }


def settings_save(timezone: str, attend_start: str, attend_end: str):
    get_db().settings.update_one(
        {"_id": _SETTINGS_ID},
        {"$set": {"timezone": timezone, "attend_start": attend_start, "attend_end": attend_end}},
        upsert=True,
    )

