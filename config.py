import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///attendance.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
    ATTEND_START = os.getenv("ATTEND_START", "00:00")
    ATTEND_END = os.getenv("ATTEND_END", "21:00")
    ADMIN_PIN = os.getenv("ADMIN_PIN", "1827")

