from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from models import Task, ActivityLog, Habit, HabitEntry
from collections import Counter
from insights import (
    build_progress_series,
    compute_category_hours,
    compute_gamification,
    detect_overload,
    most_productive_day,
    summarize_habits,
    weekly_reflection,
)

analytics_bp = Blueprint("analytics", __name__)

@analytics_bp.route("/analytics")
@login_required
def analytics():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    completed = sum(1 for t in tasks if t.status == "Completed")
    pending   = sum(1 for t in tasks if t.status == "Pending")
    missed    = sum(1 for t in tasks if t.status == "Missed")

    # Tasks per day of week
    logs = ActivityLog.query.filter_by(user_id=current_user.id).all()
    by_day = Counter(l.day_of_week for l in logs)
    daily  = [by_day.get(i, 0) for i in range(7)]

    # Category breakdown
    by_cat = Counter(t.category for t in tasks)
    category_hours = compute_category_hours(tasks)
    progress_labels, progress_values = build_progress_series(logs)
    habits = Habit.query.filter_by(user_id=current_user.id).all()
    habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
    habit_summaries = summarize_habits(habits, habit_entries)
    overload_days, burnout_warning = detect_overload(tasks)
    gamification = compute_gamification(
        tasks,
        habit_summaries,
        user_name=getattr(current_user, "name", None),
    )

    return render_template("analytics.html",
        tasks=tasks,
        completed=completed, pending=pending, missed=missed,
        daily=daily, by_cat=dict(by_cat)
        ,category_hours=category_hours
        ,progress_labels=progress_labels
        ,progress_values=progress_values
        ,most_productive=most_productive_day(logs)
        ,habit_summaries=habit_summaries
        ,weekly_reflection=weekly_reflection(tasks, logs, habit_summaries)
        ,burnout_warning=burnout_warning
        ,overload_days=overload_days
        ,gamification=gamification
    )
