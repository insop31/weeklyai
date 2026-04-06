from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    tasks         = db.relationship("Task", backref="owner", lazy=True)
    logs          = db.relationship("ActivityLog", backref="user", lazy=True)
    lists         = db.relationship("CalendarList", backref="owner", lazy=True)
    habits        = db.relationship("Habit", backref="owner", lazy=True)
    goals         = db.relationship("Goal", backref="owner", lazy=True)
    task_tags     = db.relationship("TaskTag", backref="owner", lazy=True)
    calendar_events = db.relationship("CalendarEvent", backref="owner", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    __tablename__ = "tasks"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title          = db.Column(db.String(200), nullable=False)
    category       = db.Column(db.String(100), default="Work")
    priority       = db.Column(db.Enum("Low", "Medium", "High"), default="Medium")
    deadline       = db.Column(db.DateTime)
    start_time     = db.Column(db.DateTime)
    end_time       = db.Column(db.DateTime)
    estimated_time = db.Column(db.Float, default=1.0)
    status         = db.Column(
        db.Enum("Pending", "In Progress", "Completed", "Missed"),
        default="Pending"
    )
    color          = db.Column(db.String(20), default="purple")
    attendees      = db.Column(db.Integer, default=1)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    logs = db.relationship("ActivityLog", backref="task", lazy=True)
    tags = db.relationship("TaskTag", backref="task", lazy=True, cascade="all, delete-orphan")


class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"))
    task_id         = db.Column(db.Integer, db.ForeignKey("tasks.id"))
    completion_time = db.Column(db.DateTime)
    actual_time     = db.Column(db.Float)
    day_of_week     = db.Column(db.Integer)   # 0=Mon, 6=Sun
    hour_of_day     = db.Column(db.Integer)   # 0–23
    date            = db.Column(db.Date)


class CalendarList(db.Model):
    __tablename__ = "calendar_lists"
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name    = db.Column(db.String(100))
    color   = db.Column(db.String(20), default="purple")
    items   = db.relationship("ChecklistItem", backref="list", lazy=True)


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"
    id         = db.Column(db.Integer, primary_key=True)
    list_id    = db.Column(db.Integer, db.ForeignKey("calendar_lists.id"))
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"))
    title      = db.Column(db.String(200))
    completed  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Habit(db.Model):
    __tablename__ = "habits"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    category      = db.Column(db.String(100), default="Personal")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    entries       = db.relationship("HabitEntry", backref="habit", lazy=True, cascade="all, delete-orphan")


class HabitEntry(db.Model):
    __tablename__ = "habit_entries"
    id            = db.Column(db.Integer, primary_key=True)
    habit_id      = db.Column(db.Integer, db.ForeignKey("habits.id"), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    entry_date    = db.Column(db.Date, nullable=False)
    completed     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


class Goal(db.Model):
    __tablename__ = "goals"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    period        = db.Column(db.Enum("Daily", "Weekly", "Monthly"), nullable=False)
    target_value  = db.Column(db.Integer, default=1)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


class TaskTag(db.Model):
    __tablename__ = "task_tags"
    id            = db.Column(db.Integer, primary_key=True)
    task_id       = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name          = db.Column(db.String(50), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)


class CalendarEvent(db.Model):
    __tablename__ = "calendar_events"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    event_type    = db.Column(db.String(50), default="Personal")
    event_date    = db.Column(db.Date, nullable=False)
    notes         = db.Column(db.String(300))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
