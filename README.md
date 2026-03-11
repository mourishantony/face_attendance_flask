# Face Attendance — Flask + MongoDB + HF Spaces

A mobile-friendly face-recognition attendance system.  
DeepFace (Facenet512) inference runs on **Hugging Face Spaces**; the Flask app stays lightweight and deploys on **Render** (free tier); data lives in **MongoDB Atlas**.

---

## Architecture

```
Browser / Kiosk
      │
      ▼
Flask App (Render)          ──── MongoDB Atlas (embeddings + attendance)
      │
      └──► HF Space (DeepFace API)   ◄── image → 512-d embedding
```

---

## Features

- Auto-scanning kiosk — camera starts, faces are detected and matched automatically
- Register people via **image upload** or **live 30-frame capture**
- Attendance window configurable live from the Admin panel (no redeploy)
- Auto-marks absent after window closes (APScheduler)
- Monthly CSV report per class / staff
- Admin PIN protected (set via environment variable)

---

## Project Structure

```
face_attendance_flask/
├── app.py                  # Flask routes
├── models.py               # PyMongo helpers
├── utils.py                # Calls HF Space for embeddings
├── config.py               # App config from env vars
├── templates/
│   ├── admin.html          # Add people + settings
│   ├── kiosk.html          # Auto-scan attendance
│   ├── login.html
│   ├── index.html
│   └── monthly_report.html
├── static/
│   ├── css/styles.css
│   └── js/capture.js
├── hf_space/               # ← Deploy this to Hugging Face Spaces
│   ├── app.py              #   FastAPI inference service
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
├── Dockerfile              # For the Flask app (Render)
├── docker-compose.yml      # Local dev (Flask + MongoDB)
├── render.yaml             # Render deployment config
├── requirements.txt        # Flask app dependencies (no DeepFace)
└── .env.example            # Template for all env vars
```

---

## Step 1 — Deploy the HF Space (Inference API)

This is the **first** step because the Flask app needs the Space URL to work.

### 1.1 Create a new Space

1. Go to [huggingface.co](https://huggingface.co) and log in.
2. Click your profile → **New Space**.
3. Fill in:
   - **Space name**: e.g. `face-embedding-api`
   - **License**: MIT (or your choice)
   - **SDK**: select **Docker**
   - **Visibility**: **Public**
4. Click **Create Space**.

### 1.2 Upload the Space files

You need to push the 4 files inside the `hf_space/` folder.

**Option A — Hugging Face web UI (easiest)**

1. Inside your new Space, click **Files** → **Add file** → **Upload files**.
2. Upload these 4 files one by one (do NOT upload the `hf_space/` folder itself, upload the files inside it):
   - `app.py`
   - `requirements.txt`
   - `Dockerfile`
   - `README.md`
3. Click **Commit changes to main**.

**Option B — Git (if you have `git-lfs` installed)**

```bash
# Install HF CLI once
pip install huggingface_hub

# Login
huggingface-cli login

# Clone your new space
git clone https://huggingface.co/spaces/YOUR-USERNAME/face-embedding-api
cd face-embedding-api

# Copy the 4 files from hf_space/
copy ..\hf_space\* .        # Windows
# cp ../hf_space/* .          # Mac/Linux

git add .
git commit -m "Initial deploy"
git push
```

### 1.3 Wait for the build

- Go to your Space → **App** tab. It will show **Building…** then **Running**.
- The first build takes ~5 minutes (downloads DeepFace + models).
- Once running, test it:

```bash
curl -X POST https://YOUR-USERNAME-face-embedding-api.hf.space/embed \
  -H "Content-Type: application/json" \
  -d '{"image_b64": ""}' 
# Should return {"ok": false, "error": "..."}  ← means the API is alive
```

### 1.4 Copy your Space URL

Your Space URL is:
```
https://YOUR-USERNAME-face-embedding-api.hf.space
```
You will paste this as `HF_EMBED_URL` in the Flask app env vars.

> **Note on cold starts:** Free HF Spaces sleep after ~15 min of inactivity.
> The first request after sleep takes 30–60 s. Use
> [UptimeRobot](https://uptimerobot.com) to ping `/health` every 5 minutes to keep it awake.

---

## Step 2 — Set up MongoDB Atlas

1. Go to [mongodb.com/atlas](https://www.mongodb.com/atlas) → **Create a free M0 cluster**.
2. Create a database user (username + password — no special chars in password).
3. Under **Network Access** → **Add IP Address** → **Allow access from anywhere** (`0.0.0.0/0`).
4. Click **Connect** → **Drivers** → copy the connection string:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. Replace `<username>` and `<password>` with your values. This is your `MONGODB_URI`.

---

## Step 3 — Local development

```bash
# 1. Copy env template
cp .env.example .env

# 2. Fill in .env:
#    HF_EMBED_URL=https://YOUR-USERNAME-face-embedding-api.hf.space
#    MONGODB_URI=mongodb+srv://...   (or leave as localhost for docker-compose)
#    ADMIN_PIN=your-pin

# 3a. Run with Docker Compose (includes local MongoDB — no Atlas needed for dev)
docker-compose up

# 3b. OR run directly with venv
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python app.py
```

Open [http://localhost:8000](http://localhost:8000)

---

## Step 4 — Deploy to Render

1. Push your code to GitHub (the `hf_space/` folder can be included — Render ignores it).
2. Go to [render.com](https://render.com) → **New** → **Web Service**.
3. Connect your GitHub repo.
4. Render will detect `render.yaml` automatically. Confirm **Docker** as the environment.
5. In **Environment** tab, add these variables:

   | Key | Value |
   |---|---|
   | `SECRET_KEY` | Any long random string |
   | `ADMIN_PIN` | Your PIN (digits) |
   | `MONGODB_URI` | Your Atlas connection string |
   | `MONGODB_DB` | `attendance` |
   | `HF_EMBED_URL` | Your HF Space URL (no trailing slash) |
   | `TIMEZONE` | e.g. `Asia/Kolkata` |
   | `ATTEND_START` | e.g. `08:00` |
   | `ATTEND_END` | e.g. `21:00` |

6. Click **Deploy**.
7. Once live, set up [UptimeRobot](https://uptimerobot.com) to ping `https://your-app.onrender.com/health` every 5 minutes (keeps free tier awake).

---

## Admin Panel

- **Add Person** — upload a photo or use live 30-frame camera capture
- **Registered People** — list of all enrolled people
- **Attendance Settings** — change timezone and window times without redeploying

## Kiosk

Open `/kiosk` on any device with a camera. Press **Start Camera** — faces are scanned automatically every ~1–2 seconds. No button to press.

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret |
| `ADMIN_PIN` | Yes | Login PIN for admin panel |
| `MONGODB_URI` | Yes | MongoDB connection string |
| `MONGODB_DB` | No | Database name (default: `attendance`) |
| `HF_EMBED_URL` | Yes | HF Space base URL |
| `TIMEZONE` | No | IANA timezone (default: `Asia/Kolkata`) |
| `ATTEND_START` | No | Window start HH:MM (default: `00:00`) |
| `ATTEND_END` | No | Window end HH:MM (default: `21:00`) |

---

## Recognition Threshold

The default cosine distance threshold is `0.35` in [utils.py](utils.py).  
- Lower → stricter (fewer false positives, may miss a valid face)  
- Higher → looser (more matches, risk of wrong person)

Adjust `threshold=0.35` in `match_embedding()` if needed.

