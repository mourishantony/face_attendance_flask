import os, json, io, csv
from datetime import datetime, date, time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz
import numpy as np
from functools import wraps

from config import Config
from models import db, Person, Attendance
from utils import (image_to_embedding, match_embedding, read_image_file, 
                   serialize_embedding, deserialize_embedding, b64_to_image)

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()

# ------------------ Helpers ------------------

def get_tz():
    return pytz.timezone(app.config["TIMEZONE"])

def within_attendance_window(now=None):
    tz = get_tz()
    now = now or datetime.now(tz)
    start_h, start_m = [int(x) for x in app.config["ATTEND_START"].split(":")]
    end_h, end_m = [int(x) for x in app.config["ATTEND_END"].split(":")]
    start = tz.localize(datetime.combine(now.date(), time(start_h, start_m)))
    end = tz.localize(datetime.combine(now.date(), time(end_h, end_m)))
    return start <= now <= end

def mark_absent_for_day(d: date):
    people = Person.query.all()
    for p in people:
        present = Attendance.query.filter_by(person_id=p.id, date=d, status='present').first()
        existing_absent = Attendance.query.filter_by(person_id=p.id, date=d, status='absent').first()
        if not present and not existing_absent:
            a = Attendance(person_id=p.id, date=d, status='absent',
                           timestamp=datetime.utcnow(), source='scheduler')
            db.session.add(a)
    db.session.commit()

# Scheduler to auto mark absences at end time daily
scheduler = BackgroundScheduler(timezone=app.config["TIMEZONE"])
end_h, end_m = [int(x) for x in app.config["ATTEND_END"].split(":")]
scheduler.add_job(
    func=lambda: mark_absent_for_day(datetime.now(get_tz()).date()),
    trigger=CronTrigger(hour=end_h, minute=(end_m + 5) % 60),
    id="mark_absent_daily",
    replace_existing=True,
)
scheduler.start()

# ------------------ Auth Helpers ------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ------------------ Routes ------------------

@app.route("/")
def index():
    # If not logged in → show login page
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # If logged in → show home page
    return render_template("index.html",
                           window=f"{app.config['ATTEND_START']}–{app.config['ATTEND_END']}",
                           tz=app.config['TIMEZONE'])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin = request.form.get("pin")
        if pin == app.config["ADMIN_PIN"]:
            session["logged_in"] = True
            flash("Login successful", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid PIN", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "student").strip()
        class_name = request.form.get("class_name", "").strip() or None
        image = request.files.get("image")
        if not name or not image:
            flash("Name and image are required.", "danger")
            return redirect(url_for("admin"))

        try:
            img_arr = read_image_file(image)
            emb = image_to_embedding(img_arr)
        except Exception as e:
            flash(f"Face not detected: {e}", "danger")
            return redirect(url_for("admin"))

        if Person.query.filter_by(name=name).first():
            flash("Name already exists.", "warning")
            return redirect(url_for("admin"))

        p = Person(name=name, role=role, class_name=class_name,
                   embedding=serialize_embedding(emb))
        db.session.add(p)
        db.session.commit()
        flash(f"Added {name} ({role}).", "success")
        return redirect(url_for("admin"))

    people = Person.query.order_by(Person.role.desc(),
                                   Person.class_name.asc(),
                                   Person.name.asc()).all()
    return render_template("admin.html", people=people)

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

    people = Person.query.all()
    candidates = [(p, json.loads(p.embedding)) for p in people]
    person, dist = match_embedding(emb, candidates, threshold=0.35)

    if person is None:
        return jsonify({"ok": True, "match": None, "distance": dist})

    tz_now = datetime.now(get_tz())
    if within_attendance_window(tz_now):
        today = tz_now.date()
        already = Attendance.query.filter_by(person_id=person.id,
                                             date=today, status='present').first()
        if not already:
            rec = Attendance(person_id=person.id, date=today,
                             timestamp=datetime.utcnow(),
                             status='present', source='kiosk')
            db.session.add(rec)
            db.session.commit()

    return jsonify({
        "ok": True,
        "match": {"id": person.id, "name": person.name,
                  "role": person.role, "class_name": person.class_name},
        "distance": dist,
        "within_window": within_attendance_window(tz_now),
    })


from calendar import monthrange
@app.route("/monthly_report", methods=["GET", "POST"])
@login_required
def monthly_report():
    if request.method == "POST":
        class_name = request.form.get("class_name")
        role = request.form.get("role")  # student or staff
        month = int(request.form.get("month"))
        year = int(request.form.get("year"))

        num_days = monthrange(year, month)[1]
        tz = get_tz()
        now = datetime.now(tz)
        today = now.date()

        # Parse attendance window times
        start_h, start_m = [int(x) for x in app.config["ATTEND_START"].split(":")]
        end_h, end_m = [int(x) for x in app.config["ATTEND_END"].split(":")]
        today_start = tz.localize(datetime.combine(today, time(start_h, start_m)))
        today_end = tz.localize(datetime.combine(today, time(end_h, end_m)))

        # Query people
        if role == "student":
            people = Person.query.filter_by(class_name=class_name, role="student").all()
        else:  # staff
            people = Person.query.filter_by(role="staff").all()

        # Build CSV
        header = ["S.No", "Name"] + [f"{day:02d}" for day in range(1, num_days + 1)]
        rows = [header]

        for idx, p in enumerate(people, start=1):
            row = [idx, p.name]
            for d in range(1, num_days + 1):
                dt = date(year, month, d)

                if dt < today:
                    # Past days → mark normally
                    mark_absent_for_day(dt)
                    rec = (
                        Attendance.query.filter_by(person_id=p.id, date=dt, status="present")
                        .order_by(Attendance.timestamp.asc())
                        .first()
                    )
                    if rec:
                        local_ts = rec.timestamp.astimezone(get_tz())
                        cell = f"Present ({local_ts.strftime('%H:%M:%S')})"
                    else:
                        cell = "Absent"

                elif dt == today:
                    if now < today_start:
                        # Attendance window not started → leave blank
                        cell = ""
                    elif today_start <= now <= today_end:
                        # Window running → check if marked present, else blank
                        rec = (
                            Attendance.query.filter_by(person_id=p.id, date=dt, status="present")
                            .order_by(Attendance.timestamp.asc())
                            .first()
                        )
                        if rec:
                            local_ts = rec.timestamp.astimezone(get_tz())
                            cell = f"Present ({local_ts.strftime('%H:%M:%S')})"
                        else:
                            cell = ""
                    else:
                        # After window closed → mark absent if not present
                        mark_absent_for_day(dt)
                        rec = (
                            Attendance.query.filter_by(person_id=p.id, date=dt, status="present")
                            .order_by(Attendance.timestamp.asc())
                            .first()
                        )
                        if rec:
                            local_ts = rec.timestamp.astimezone(get_tz())
                            cell = f"Present ({local_ts.strftime('%H:%M:%S')})"
                        else:
                            cell = "Absent"

                else:
                    # Future days → leave blank
                    cell = ""

                row.append(cell)
            rows.append(row)

        # Return CSV
        mem = io.StringIO()
        writer = csv.writer(mem)
        writer.writerows(rows)
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

    # Collect available classes for dropdown
    classes = db.session.query(Person.class_name).distinct().all()
    return render_template(
        "monthly_report.html",
        classes=[c[0] for c in classes if c[0]],
        current_year=datetime.now().year,
    )

@app.route("/kiosk")
def kiosk():
    return render_template("kiosk.html",
                           window=f"{app.config['ATTEND_START']}–{app.config['ATTEND_END']}",
                           tz=app.config['TIMEZONE'])

@app.route("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
