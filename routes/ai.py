from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Task, ActivityLog, Habit, HabitEntry
from ml_model import train_model, recommend_schedule
from insights import compute_gamification, detect_overload, summarize_habits, weekly_reflection

ai_bp = Blueprint("ai", __name__)

@ai_bp.route("/ai_recommendations")
@login_required
def ai_recommendations():
    # Re-train model on latest data
    train_model(current_user.id, db, ActivityLog, Task)

    pending = Task.query.filter(
        Task.user_id == current_user.id,
        Task.status.in_(["Pending", "In Progress"])
    ).all()

    recs = recommend_schedule(current_user.id, pending, db, ActivityLog, Task)
    all_tasks = Task.query.filter_by(user_id=current_user.id).all()
    logs = ActivityLog.query.filter_by(user_id=current_user.id).all()
    habits = Habit.query.filter_by(user_id=current_user.id).all()
    habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
    habit_summaries = summarize_habits(habits, habit_entries)
    overload_days, burnout_warning = detect_overload(all_tasks)

    return render_template(
        "recommendations.html",
        tasks=all_tasks,
        recommendations=recs,
        burnout_warning=burnout_warning,
        overload_days=overload_days,
        weekly_reflection=weekly_reflection(all_tasks, logs, habit_summaries),
        gamification=compute_gamification(all_tasks, habit_summaries),
    )
