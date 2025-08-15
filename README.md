# Face Attendance (Flask + DeepFace)

A mobile-friendly face recognition attendance system for tuition classes.

## Features
- Store students & staff with face embeddings (DeepFace / Facenet512)
- Kiosk page for mobile phones (uses device camera)
- Attendance window (default 18:00–21:00 IST) — outside this, scans don't mark present
- Auto-mark ABSENT after window closes
- Admin page to add new people (with Admin PIN)
- CSV report per day grouped by class
- SQLite database, embeddings stored alongside people (no external pickle needed)

> Note: You asked for a pickle file; here, embeddings are stored in the database as JSON.
> If you strictly need a `.pickle`, you can export/import via a small adapter (see below).

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # optionally change ADMIN_PIN and times
python app.py
```

Open http://localhost:8000, go to **Admin** to add students & staff (one image each).  
Use **Kiosk** on a phone to scan and mark attendance.

## Export / Import embeddings to pickle (optional)

```python
# export_pickle.py
import pickle, json
from app import app, db, Person
with app.app_context():
    data = { p.name: json.loads(p.embedding) for p in Person.query.all() }
with open("embeddings.pickle", "wb") as f:
    pickle.dump(data, f)
print("Wrote embeddings.pickle")
```

```python
# import_pickle.py
import pickle, json
from app import app, db, Person
with open("embeddings.pickle", "rb") as f:
    data = pickle.load(f)
with app.app_context():
    for name, emb in data.items():
        if not Person.query.filter_by(name=name).first():
            db.session.add(Person(name=name, role="student", class_name=None, embedding=json.dumps(emb)))
    db.session.commit()
print("Imported from pickle")
```

## Deployment tips

- **Gunicorn**: `gunicorn -w 2 -b 0.0.0.0:8000 app:app`
- Use a reverse proxy (Nginx) with HTTPS (Let's Encrypt)
- Ensure your hosting has AVX support (for DeepFace/TF). If not, consider CPU-friendly backends or `opencv` embeddings.
- For truly offline edge devices, pre-install models during build.

## Notes

- Threshold (`0.35`) is tuned conservatively; adjust in `utils.py` if needed.
- To handle ~100 students across classes, the cosine search over embeddings is lightweight and runs in milliseconds on CPU.
- If you prefer **OpenCV Haar** for detection, change `detector_backend` in `utils.py`.
