from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from models import db, Task, ActivityLog, CalendarList, ChecklistItem, Habit, HabitEntry, Goal, TaskTag, CalendarEvent
from insights import build_recent_completion_feed, compute_gamification, compute_priority_score, infer_task_metadata, next_occurrence, summarize_habits
from ml_model import get_productive_slots

tasks_bp = Blueprint("tasks", __name__)


def priority_to_color(priority):
    mapping = {
        "High": "lime",
        "Medium": "purple",
        "Low": "pink",
    }
    return mapping.get(priority, "purple")

@tasks_bp.route("/add_task", methods=["POST"])
@login_required
def add_task():
    d = request.form
    inferred_category, inferred_tags = infer_task_metadata(
        d.get("title", ""),
        d.get("category", "Work"),
        d.get("tags", ""),
    )
    priority = d.get("priority", "Medium")
    task = Task(
        user_id        = current_user.id,
        title          = d.get("title", "").strip(),
        category       = inferred_category,
        priority       = priority,
        start_time     = datetime.fromisoformat(d["start_time"]) if d.get("start_time") else None,
        end_time       = datetime.fromisoformat(d["end_time"])   if d.get("end_time")   else None,
        deadline       = datetime.fromisoformat(d["deadline"])   if d.get("deadline")   else None,
        estimated_time = float(d.get("estimated_time", 1)),
        color          = priority_to_color(priority),
        attendees      = int(d.get("attendees", 1)),
    )
    db.session.add(task)
    db.session.flush()

    for tag in inferred_tags:
        db.session.add(TaskTag(task_id=task.id, user_id=current_user.id, name=tag))

    db.session.commit()
    return redirect(url_for("main.dashboard"))


@tasks_bp.route("/tasks")
@login_required
def get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    tasks = sorted(
        tasks,
        key=lambda task: (
            getattr(task, "status", "") == "Completed",
            -compute_priority_score(task),
            getattr(task, "deadline", None) or getattr(task, "start_time", None) or getattr(task, "created_at", datetime.utcnow()),
        ),
    )
    return jsonify([{
        "id": t.id, "title": t.title, "category": t.category,
        "priority": t.priority, "status": t.status, "color": priority_to_color(t.priority),
        "start_time": t.start_time.isoformat() if t.start_time else None,
        "end_time":   t.end_time.isoformat()   if t.end_time   else None,
        "tags": [tag.name for tag in t.tags],
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "smart_priority": compute_priority_score(t),
    } for t in tasks])


@tasks_bp.route("/update_task/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    previous_status = task.status

    for field in ["title", "category", "priority", "status"]:
        if field in data:
            setattr(task, field, data[field])

    if "priority" in data:
        task.color = priority_to_color(task.priority)

    if "start_time" in data:
        task.start_time = datetime.fromisoformat(data["start_time"]) if data["start_time"] else None
    if "end_time" in data:
        task.end_time   = datetime.fromisoformat(data["end_time"]) if data["end_time"] else None

    # Log completion to activity_log
    if data.get("status") == "Completed" and previous_status != "Completed":
        now = datetime.utcnow()
        log = ActivityLog(
            user_id         = current_user.id,
            task_id         = task.id,
            completion_time = now,
            actual_time     = task.estimated_time,
            day_of_week     = now.weekday(),
            hour_of_day     = now.hour,
            date            = now.date(),
        )
        db.session.add(log)

    if data.get("status") == "Missed":
        slots = get_productive_slots(current_user.id, db, ActivityLog)
        if slots:
            target = next_occurrence(slots[0][0], slots[0][1])
            duration_hours = float(task.estimated_time or 1.0)
            task.start_time = target
            task.end_time = target + timedelta(hours=duration_hours)
            task.status = "Pending"

    db.session.commit()

    tasks = Task.query.filter_by(user_id=current_user.id).all()
    logs = ActivityLog.query.filter_by(user_id=current_user.id).all()
    habits = Habit.query.filter_by(user_id=current_user.id).all()
    habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
    gamification = compute_gamification(tasks, summarize_habits(habits, habit_entries))
    recent_completions = build_recent_completion_feed(tasks, logs)

    return jsonify({
        "success": True,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
        },
        "gamification": gamification,
        "recent_completions": recent_completions,
    })


@tasks_bp.route("/delete_task/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({"success": True})


@tasks_bp.route("/move_task/<int:task_id>", methods=["PATCH"])
@login_required
def move_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    task.start_time = datetime.fromisoformat(data["start_time"])
    task.end_time   = datetime.fromisoformat(data["end_time"])
    db.session.commit()
    return jsonify({"success": True})


@tasks_bp.route("/smart_reschedule/<int:task_id>", methods=["POST"])
@login_required
def smart_reschedule(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    slots = get_productive_slots(current_user.id, db, ActivityLog)
    target = next_occurrence(*(slots[0] if slots else (0, 9)))
    duration_hours = float(task.estimated_time or 1.0)
    task.start_time = target
    task.end_time = target + timedelta(hours=duration_hours)
    task.status = "Pending"
    db.session.commit()
    return jsonify({
        "success": True,
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "end_time": task.end_time.isoformat() if task.end_time else None,
    })


@tasks_bp.route("/add_habit", methods=["POST"])
@login_required
def add_habit():
    title = request.form.get("title", "").strip()
    if not title:
        return redirect(url_for("main.dashboard"))

    habit = Habit(
        user_id=current_user.id,
        title=title,
        category=request.form.get("category", "Personal"),
    )
    db.session.add(habit)
    db.session.commit()
    return redirect(url_for("main.dashboard"))


@tasks_bp.route("/toggle_habit/<int:habit_id>", methods=["PATCH"])
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    entry_day = date.fromisoformat(payload.get("date")) if payload.get("date") else date.today()

    entry = HabitEntry.query.filter_by(
        habit_id=habit.id,
        user_id=current_user.id,
        entry_date=entry_day,
    ).first()

    if entry:
        db.session.delete(entry)
        completed = False
    else:
        db.session.add(HabitEntry(
            habit_id=habit.id,
            user_id=current_user.id,
            entry_date=entry_day,
            completed=True,
        ))
        completed = True

    db.session.commit()
    return jsonify({"success": True, "completed": completed})


@tasks_bp.route("/add_goal", methods=["POST"])
@login_required
def add_goal():
    title = request.form.get("title", "").strip()
    if not title:
        return redirect(url_for("main.dashboard"))

    goal = Goal(
        user_id=current_user.id,
        title=title,
        period=request.form.get("period", "Weekly"),
        target_value=int(request.form.get("target_value", 1) or 1),
    )
    db.session.add(goal)
    db.session.commit()
    return redirect(url_for("main.dashboard"))


@tasks_bp.route("/add_calendar_event", methods=["POST"])
@login_required
def add_calendar_event():
    title = request.form.get("title", "").strip()
    event_date = request.form.get("event_date", "").strip()
    if not title or not event_date:
        return redirect(url_for("main.dashboard"))

    event = CalendarEvent(
        user_id=current_user.id,
        title=title,
        event_type=request.form.get("event_type", "Personal"),
        event_date=date.fromisoformat(event_date),
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.add(event)
    db.session.commit()
    return redirect(url_for("main.dashboard"))


@tasks_bp.route("/toggle_checklist/<int:item_id>", methods=["PATCH"])
@login_required
def toggle_checklist(item_id):
    item = ChecklistItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    item.completed = bool(payload.get("completed"))
    db.session.commit()
    return jsonify({"success": True, "completed": item.completed})
