from flask import Flask, render_template
from flask_login import LoginManager
from config import config
from models import db, User, Task, ActivityLog, CalendarList, ChecklistItem, Habit, HabitEntry, Goal, CalendarEvent
from routes.auth import auth_bp
from routes.tasks import tasks_bp
from routes.analytics import analytics_bp
from routes.ai import ai_bp
from datetime import datetime, timedelta
import sys
from insights import (
    compute_gamification,
    compute_goal_progress,
    compute_priority_score,
    detect_overload,
    is_urgent,
    summarize_habits,
    weekly_reflection,
)

def create_app(env="development"):
    app = Flask(__name__)
    app.config.from_object(config[env])

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(ai_bp)

    from flask import Blueprint
    from flask_login import login_required, current_user
    main_bp = Blueprint("main", __name__)

    @main_bp.route("/")
    @main_bp.route("/dashboard")
    @login_required
    def dashboard():
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        lists = CalendarList.query.filter_by(user_id=current_user.id).all()
        habits = Habit.query.filter_by(user_id=current_user.id).all()
        habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
        goals = Goal.query.filter_by(user_id=current_user.id).all()
        logs = ActivityLog.query.filter_by(user_id=current_user.id).all()
        calendar_events = CalendarEvent.query.filter_by(user_id=current_user.id).order_by(
            CalendarEvent.event_date.asc(),
            CalendarEvent.created_at.asc()
        ).all()

        habit_summaries = summarize_habits(habits, habit_entries)
        goal_progress = compute_goal_progress(goals, tasks, habit_summaries)
        gamification = compute_gamification(tasks, habit_summaries)
        overload_days, burnout_warning = detect_overload(tasks)
        urgent_tasks = sorted(
            [task for task in tasks if is_urgent(task)],
            key=lambda item: compute_priority_score(item),
            reverse=True,
        )[:5]

        return render_template(
            "dashboard.html",
            tasks=tasks,
            cal_lists=lists,
            habit_summaries=habit_summaries,
            goal_progress=goal_progress,
            gamification=gamification,
            urgent_tasks=urgent_tasks,
            burnout_warning=burnout_warning,
            overload_days=overload_days,
            weekly_reflection=weekly_reflection(tasks, logs, habit_summaries),
            calendar_events=calendar_events,
        )

    @main_bp.route("/task-list")
    @login_required
    def task_list():
        tasks = Task.query.filter_by(user_id=current_user.id).order_by(
            Task.start_time.is_(None),
            Task.start_time.asc(),
            Task.created_at.desc()
        ).all()
        habits = Habit.query.filter_by(user_id=current_user.id).all()
        habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
        return render_template(
            "tasks.html",
            tasks=tasks,
            gamification=compute_gamification(tasks, summarize_habits(habits, habit_entries)),
        )

    @main_bp.route("/messages")
    @login_required
    def messages():
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        logs = ActivityLog.query.filter_by(user_id=current_user.id).order_by(
            ActivityLog.completion_time.desc()
        ).limit(20).all()
        habits = Habit.query.filter_by(user_id=current_user.id).all()
        habit_entries = HabitEntry.query.filter_by(user_id=current_user.id).all()
        return render_template(
            "messages.html",
            tasks=tasks,
            logs=logs,
            weekly_reflection=weekly_reflection(tasks, logs, summarize_habits(habits, habit_entries)),
        )

    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    return app


def seed_data(app):
    with app.app_context():
        if User.query.first():
            print("DB already seeded.")
            return

        # Demo user
        user = User(name="Alex", email="demo@weeklyai.com")
        user.set_password("demo1234")
        db.session.add(user)
        db.session.flush()

        # Calendar lists
        my_cal   = CalendarList(user_id=user.id, name="My Calendar",    color="purple")
        other_cal= CalendarList(user_id=user.id, name="Other Calendar", color="lime")
        db.session.add_all([my_cal, other_cal])
        db.session.flush()

        # Checklist items
        db.session.add_all([
            ChecklistItem(list_id=my_cal.id,    user_id=user.id, title="Yoga Exercise With Friends"),
            ChecklistItem(list_id=my_cal.id,    user_id=user.id, title="Cardio Training On Sundays", completed=True),
            ChecklistItem(list_id=other_cal.id, user_id=user.id, title="Indonesian National Holiday", completed=True),
            ChecklistItem(list_id=other_cal.id, user_id=user.id, title="Saturday Holiday With Team",  completed=True),
        ])

        # Seed tasks across current week
        now  = datetime.utcnow()
        mon  = now - timedelta(days=now.weekday())
        cats = ["Work", "Health", "Personal", "Study", "Work", "Health",
                "Personal", "Work", "Study", "Health", "Work", "Personal"]
        pris = ["High","Medium","Low","High","Medium","High",
                "Low","Medium","High","Low","Medium","High"]
        cols = ["lime","purple","purple","lime","purple","lime",
                "purple","lime","purple","purple","lime","purple"]
        titles = [
            "Morning Run", "Yoga Exercise", "API Development", "Code Review",
            "Cardio Exercise", "Sprint Retrospective", "Read Research Paper",
            "Cardio Burned", "Database Review", "Team Standup",
            "Client Meeting", "Weekly Planning",
        ]

        tasks_created = []
        for i, title in enumerate(titles):
            day_offset = i % 7
            hour       = 9 + (i % 4)
            start      = mon + timedelta(days=day_offset, hours=hour)
            end        = start + timedelta(hours=1)
            status     = "Completed" if i < 5 else ("Missed" if i == 5 else "Pending")
            t = Task(
                user_id=user.id, title=title,
                category=cats[i], priority=pris[i],
                start_time=start, end_time=end, deadline=end,
                estimated_time=1.0, status=status,
                color=cols[i], attendees=max(1, i % 4),
            )
            db.session.add(t)
            tasks_created.append(t)

        db.session.flush()

        # Activity log entries for ML training
        for i, t in enumerate(tasks_created[:12]):
            if t.status == "Completed":
                log = ActivityLog(
                    user_id=user.id, task_id=t.id,
                    completion_time=t.end_time,
                    actual_time=t.estimated_time,
                    day_of_week=t.start_time.weekday(),
                    hour_of_day=t.start_time.hour,
                    date=t.start_time.date(),
                )
                db.session.add(log)

        # Extra log entries to reach 15 total
        for i in range(10):
            log = ActivityLog(
                user_id=user.id, task_id=tasks_created[0].id,
                completion_time=now - timedelta(days=i),
                actual_time=1.0,
                day_of_week=(now - timedelta(days=i)).weekday(),
                hour_of_day=9 + (i % 3),
                date=(now - timedelta(days=i)).date(),
            )
            db.session.add(log)

        db.session.commit()
        print("Seeded: demo@weeklyai.com / demo1234")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    if "seed" in sys.argv:
        seed_data(app)
    else:
        app.run(debug=True)
