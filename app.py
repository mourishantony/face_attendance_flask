import os, io, csv
from calendar import monthrange
from datetime import datetime, date, time
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, session)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz

from config import Config
from models import (init_db, person_all, person_find_by_name, person_create,
                    person_distinct_classes, attendance_mark_present,
                    attendance_mark_absent, attendance_for_person_date,
                    settings_get, settings_save)
from utils import (image_to_embedding, batch_image_to_embeddings, match_embedding,
                   read_image_file, b64_to_image, average_embeddings)

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config)

# Init MongoDB
mongo_db = init_db(app)

# ------------------ Live settings (DB overrides env defaults) ------------------

def load_settings():
    defaults = {
        "TIMEZONE":     app.config["TIMEZONE"],
        "ATTEND_START": app.config["ATTEND_START"],
        "ATTEND_END":   app.config["ATTEND_END"],
    }
    return settings_get(defaults)


def get_tz():
    return pytz.timezone(load_settings()["TIMEZONE"])


def within_attendance_window(now=None):
    cfg = load_settings()
    tz = pytz.timezone(cfg["TIMEZONE"])
    now = now or datetime.now(tz)
    start_h, start_m = [int(x) for x in cfg["ATTEND_START"].split(":")]
    end_h,   end_m   = [int(x) for x in cfg["ATTEND_END"].split(":")]
    start = tz.localize(datetime.combine(now.date(), time(start_h, start_m)))
    end   = tz.localize(datetime.combine(now.date(), time(end_h,   end_m)))
    return start <= now <= end


def mark_absent_for_day(d: date):
    tz = get_tz()
    now_local = datetime.now(tz)
    for p in person_all():
        pid = str(p["_id"])
        attendance_mark_absent(pid, d, now_local)


# ------------------ Scheduler ------------------

scheduler = BackgroundScheduler(timezone=app.config["TIMEZONE"])

def _scheduled_absent():
    tz = get_tz()
    mark_absent_for_day(datetime.now(tz).date())

def _reschedule():
    cfg = load_settings()
    end_h, end_m = [int(x) for x in cfg["ATTEND_END"].split(":")]
    trigger_min = (end_m + 5) % 60
    trigger_hr  = end_h if (end_m + 5) < 60 else (end_h + 1) % 24
    scheduler.add_job(
        func=_scheduled_absent,
        trigger=CronTrigger(hour=trigger_hr, minute=trigger_min,
                            timezone=cfg["TIMEZONE"]),
        id="mark_absent_daily",
        replace_existing=True,
    )

_reschedule()
scheduler.start()

# ------------------ Auth ------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ------------------ Routes ------------------

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    cfg = load_settings()
    return render_template("index.html",
                           window=f"{cfg['ATTEND_START']}–{cfg['ATTEND_END']}",
                           tz=cfg["TIMEZONE"])


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("pin") == app.config["ADMIN_PIN"]:
            session["logged_in"] = True
            flash("Login successful", "success")
            return redirect(url_for("index"))
        flash("Invalid PIN", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))


# ------------------ Admin ------------------

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if request.method == "POST":
        action = request.form.get("action", "add_person")

        # ── Save settings ──────────────────────────────────────────
        if action == "save_settings":
            timezone     = request.form.get("timezone", "").strip()
            attend_start = request.form.get("attend_start", "").strip()
            attend_end   = request.form.get("attend_end", "").strip()
            if not timezone or not attend_start or not attend_end:
                flash("All settings fields are required.", "danger")
            else:
                try:
                    pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    flash(f"Unknown timezone: {timezone}", "danger")
                    return redirect(url_for("admin"))
                settings_save(timezone, attend_start, attend_end)
                _reschedule()
                flash("Settings saved.", "success")
            return redirect(url_for("admin"))

        # ── Add person (upload image) ──────────────────────────────
        name       = request.form.get("name", "").strip()
        role       = request.form.get("role", "student").strip()
        class_name = request.form.get("class_name", "").strip() or None
        image      = request.files.get("image")

        if not name or not image:
            flash("Name and image are required.", "danger")
            return redirect(url_for("admin"))

        if person_find_by_name(name):
            flash("Name already exists.", "warning")
            return redirect(url_for("admin"))

        try:
            img_arr = read_image_file(image)
            emb = image_to_embedding(img_arr)
        except Exception as e:
            flash(f"Face not detected: {e}", "danger")
            return redirect(url_for("admin"))

        person_create(name, role, class_name, emb)
        flash(f"Added {name} ({role}).", "success")
        return redirect(url_for("admin"))

    cfg = load_settings()
    people = person_all()
    return render_template("admin.html", people=people, settings=cfg)


# ------------------ API: Kiosk recognition ------------------

@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    data = request.get_json(silent=True)
    file = request.files.get("image")

    if data and "image_b64" in data:
        img_arr = b64_to_image(data["image_b64"])
    elif file:
        img_arr = read_image_file(file)
    else:
        return jsonify({"ok": False, "error": "No image provided"}), 400

    try:
        emb = image_to_embedding(img_arr)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Face not detected: {e}"}), 400

    people = person_all()
    candidates = [(p, p["embedding"]) for p in people]
    person, dist = match_embedding(emb, candidates, threshold=0.35)

    if person is None:
        return jsonify({"ok": True, "match": None, "distance": dist})

    tz = get_tz()
    tz_now = datetime.now(tz)
    pid = str(person["_id"])

    if within_attendance_window(tz_now):
        attendance_mark_present(pid, tz_now.date(), tz_now)

    return jsonify({
        "ok": True,
        "match": {
            "id":         pid,
            "name":       person["name"],
            "role":       person["role"],
            "class_name": person.get("class_name"),
        },
        "distance":      dist,
        "within_window": within_attendance_window(tz_now),
    })


# ------------------ API: Live registration ------------------

@app.route("/api/register_live", methods=["POST"])
@login_required
def api_register_live():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "No data provided"}), 400

    name       = (data.get("name") or "").strip()
    role       = (data.get("role") or "student").strip()
    class_name = (data.get("class_name") or "").strip() or None
    frames     = data.get("frames", [])

    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400
    if not frames:
        return jsonify({"ok": False, "error": "No frames provided"}), 400
    if person_find_by_name(name):
        return jsonify({"ok": False, "error": "Name already exists"}), 409

    imgs = []
    for frame_b64 in frames:
        try:
            imgs.append(b64_to_image(frame_b64))
        except Exception:
            continue

    try:
        embeddings = batch_image_to_embeddings(imgs)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 503

    if not embeddings:
        return jsonify({"ok": False, "error": "No face detected in any captured frame"}), 400

    final_emb = average_embeddings(embeddings)
    person_create(name, role, class_name, final_emb)
    return jsonify({"ok": True, "name": name, "frames_used": len(embeddings)})


# ------------------ Kiosk ------------------

@app.route("/kiosk")
def kiosk():
    cfg = load_settings()
    return render_template("kiosk.html",
                           window=f"{cfg['ATTEND_START']}–{cfg['ATTEND_END']}",
                           tz=cfg["TIMEZONE"])


# ------------------ Monthly report ------------------

@app.route("/monthly_report", methods=["GET", "POST"])
@login_required
def monthly_report():
    if request.method == "POST":
        class_name = request.form.get("class_name")
        role       = request.form.get("role")
        month      = int(request.form.get("month"))
        year       = int(request.form.get("year"))

        cfg = load_settings()
        tz  = pytz.timezone(cfg["TIMEZONE"])
        now = datetime.now(tz)
        today = now.date()

        num_days = monthrange(year, month)[1]
        start_h, start_m = [int(x) for x in cfg["ATTEND_START"].split(":")]
        end_h,   end_m   = [int(x) for x in cfg["ATTEND_END"].split(":")]
        today_start = tz.localize(datetime.combine(today, time(start_h, start_m)))
        today_end   = tz.localize(datetime.combine(today, time(end_h,   end_m)))

        all_people = person_all()
        if role == "student":
            people = [p for p in all_people
                      if p["role"] == "student" and p.get("class_name") == class_name]
        else:
            people = [p for p in all_people if p["role"] == "staff"]

        header = ["S.No", "Name"]
        for d in range(1, num_days + 1):
            header += [f"{d:02d} Enter", f"{d:02d} Exit"]
        rows = [header]

        for idx, p in enumerate(people, start=1):
            pid = str(p["_id"])
            row = [idx, p["name"]]
            for d in range(1, num_days + 1):
                dt = date(year, month, d)
                enter_time = exit_time = ""

                if dt < today:
                    mark_absent_for_day(dt)
                    recs = attendance_for_person_date(pid, dt, "present")
                    if recs:
                        enter_time = recs[0]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                        exit_time  = recs[-1]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                    else:
                        enter_time = exit_time = "Absent"

                elif dt == today:
                    if now < today_start:
                        pass
                    elif today_start <= now <= today_end:
                        recs = attendance_for_person_date(pid, dt, "present")
                        if recs:
                            enter_time = recs[0]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                            exit_time  = recs[-1]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                    else:
                        mark_absent_for_day(dt)
                        recs = attendance_for_person_date(pid, dt, "present")
                        if recs:
                            enter_time = recs[0]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                            exit_time  = recs[-1]["timestamp"].astimezone(tz).strftime("%H:%M:%S")
                        else:
                            enter_time = exit_time = "Absent"

                row += [enter_time, exit_time]
            rows.append(row)

        mem = io.StringIO()
        csv.writer(mem).writerows(rows)
        mem.seek(0)
        filename = (
            f"attendance_{role}_{class_name}_{year}-{month:02d}.csv"
            if role == "student"
            else f"attendance_staff_{year}-{month:02d}.csv"
        )
        return send_file(
            io.BytesIO(mem.getvalue().encode("utf-8")),
            as_attachment=True,
            download_name=filename,
            mimetype="text/csv",
        )

    return render_template(
        "monthly_report.html",
        classes=person_distinct_classes(),
        current_year=datetime.now().year,
    )


# ------------------ Health ------------------

@app.route("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), debug=True)
