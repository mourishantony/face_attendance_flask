from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Person(db.Model):
    __tablename__ = "people"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, unique=True)
    role = db.Column(db.String, nullable=False)  # 'student' or 'staff'
    class_name = db.Column(db.String, nullable=True)  # for students
    # store embedding vector as JSON text for portability
    embedding = db.Column(db.Text, nullable=False)

class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String, nullable=False)  # 'present' or 'absent'
    source = db.Column(db.String, nullable=True)  # 'kiosk'/'admin'/'import'

    person = db.relationship("Person", backref="attendance")
