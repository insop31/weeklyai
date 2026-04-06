from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta


CATEGORY_KEYWORDS = {
    "Study": {
        "keywords": ["study", "assignment", "exam", "revision", "notes", "homework", "dbms", "database", "coding practice", "practice"],
        "tags": ["Learning", "Deep Work"],
    },
    "Work": {
        "keywords": ["client", "meeting", "review", "deploy", "sprint", "api", "database review", "presentation", "email", "project"],
        "tags": ["Professional", "Collaboration"],
    },
    "Health": {
        "keywords": ["run", "exercise", "workout", "gym", "cardio", "yoga", "walk", "sleep", "meditation"],
        "tags": ["Wellness", "Energy"],
    },
    "Personal": {
        "keywords": ["family", "groceries", "call", "clean", "travel", "plan", "journal", "read"],
        "tags": ["Life", "Errand"],
    },
}


def infer_task_metadata(title, category=None, raw_tags=""):
    text = (title or "").strip().lower()
    explicit_category = (category or "").strip()

    if explicit_category and explicit_category not in {"", "Auto"}:
        inferred_category = explicit_category
    else:
        inferred_category = "Work"
        best_score = -1
        for name, rule in CATEGORY_KEYWORDS.items():
            score = sum(1 for keyword in rule["keywords"] if keyword in text)
            if score > best_score:
                inferred_category = name
                best_score = score

    tags = []
    for chunk in (raw_tags or "").split(","):
        tag = chunk.strip()
        if tag and tag not in tags:
            tags.append(tag)

    for name, rule in CATEGORY_KEYWORDS.items():
        if name == inferred_category:
            for tag in rule["tags"]:
                if tag not in tags:
                    tags.append(tag)

    # Lightweight NLP-style subcategory cues from the task text.
    if "database" in text or "dbms" in text:
        tags.append("Database")
    if "reading" in text or "read" in text:
        tags.append("Reading")
    if "coding" in text or "api" in text:
        tags.append("Coding")
    if "exercise" in text or "cardio" in text:
        tags.append("Exercise")

    return inferred_category, list(dict.fromkeys(tags))


def compute_priority_score(task, now=None):
    now = now or datetime.utcnow()
    base = {"Low": 25, "Medium": 50, "High": 80}.get(getattr(task, "priority", "Medium"), 50)
    hours = float(getattr(task, "estimated_time", 1.0) or 1.0)
    difficulty_bonus = min(int(hours * 6), 24)
    category_bonus = {"Study": 8, "Work": 6, "Health": 3, "Personal": 2}.get(getattr(task, "category", "Work"), 0)

    deadline_bonus = 0
    deadline = getattr(task, "deadline", None)
    if deadline:
        hours_left = (deadline - now).total_seconds() / 3600
        if hours_left <= 0:
            deadline_bonus = 40
        elif hours_left <= 24:
            deadline_bonus = 32
        elif hours_left <= 72:
            deadline_bonus = 20
        elif hours_left <= 168:
            deadline_bonus = 10

    missed_bonus = 18 if getattr(task, "status", "") == "Missed" else 0
    return max(0, min(100, base + difficulty_bonus + category_bonus + deadline_bonus + missed_bonus))


def is_urgent(task, now=None):
    now = now or datetime.utcnow()
    deadline = getattr(task, "deadline", None)
    if getattr(task, "status", "") == "Completed":
        return False
    if getattr(task, "priority", "") == "High":
        return True
    return bool(deadline and deadline <= now + timedelta(days=1))


def recommend_subtasks(task):
    hours = float(getattr(task, "estimated_time", 1.0) or 1.0)
    if hours < 2.5:
        return []

    title = getattr(task, "title", "Task")
    steps = [
        f"Plan the approach for {title}",
        f"Do the first focused work block for {title}",
        f"Review and wrap up {title}",
    ]
    if hours >= 5:
        steps.insert(2, f"Take a break and continue the second work block for {title}")
    return steps


def build_progress_series(logs, weeks=4):
    today = date.today()
    start = today - timedelta(days=today.weekday() + (weeks - 1) * 7)
    labels = []
    values = []

    for index in range(weeks):
        week_start = start + timedelta(days=index * 7)
        week_end = week_start + timedelta(days=6)
        labels.append(
            "This week" if index == weeks - 1 else week_start.strftime("%b %d")
        )
        values.append(
            sum(
                1
                for log in logs
                if log.date is not None and week_start <= log.date <= week_end
            )
        )
    return labels, values


def compute_category_hours(tasks):
    hours = defaultdict(float)
    for task in tasks:
        hours[getattr(task, "category", "Work") or "Work"] += float(getattr(task, "estimated_time", 1.0) or 1.0)
    return dict(hours)


def most_productive_day(logs):
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    counts = Counter(log.day_of_week for log in logs if log.day_of_week is not None)
    if not counts:
        return "No clear pattern yet"
    return names[counts.most_common(1)[0][0]]


def detect_overload(tasks):
    daily_hours = defaultdict(float)
    overloaded_days = []

    for task in tasks:
        if getattr(task, "status", "") == "Completed":
            continue
        task_start = getattr(task, "start_time", None)
        task_day = task_start.date() if task_start else None
        if task_day:
            daily_hours[task_day] += float(getattr(task, "estimated_time", 1.0) or 1.0)

    for day, total in sorted(daily_hours.items()):
        if total >= 8:
            overloaded_days.append({"day": day.strftime("%A"), "hours": round(total, 1)})

    warning = None
    if len(overloaded_days) >= 2:
        warning = "Your schedule may cause fatigue. Consider adding breaks or moving tasks away from overloaded days."
    elif overloaded_days:
        warning = f"{overloaded_days[0]['day']} looks overloaded. Consider rescheduling a task to protect your focus."

    return overloaded_days, warning


def suggest_reschedule_slot(task, slots):
    if not slots:
        return None

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    best_day, best_hour = slots[0]
    return f"{names[best_day]} {best_hour}:00"


def summarize_habits(habits, entries):
    entry_map = defaultdict(set)
    for entry in entries:
        if entry.completed:
            entry_map[entry.habit_id].add(entry.entry_date)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]

    summaries = []
    for habit in habits:
        completed_days = entry_map.get(habit.id, set())

        streak = 0
        cursor = today
        while cursor in completed_days:
            streak += 1
            cursor -= timedelta(days=1)

        week_completed = sum(1 for day in week_days if day in completed_days)
        percentage = int((week_completed / 7) * 100)

        summaries.append({
            "habit": habit,
            "streak": streak,
            "percentage": percentage,
            "completed_today": today in completed_days,
        })

    return summaries


def compute_goal_progress(goals, tasks, habit_summaries):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    completed_today = sum(
        1 for task in tasks
        if getattr(task, "status", "") == "Completed"
        and getattr(task, "end_time", None)
        and task.end_time.date() == today
    )
    completed_week = sum(
        1 for task in tasks
        if getattr(task, "status", "") == "Completed"
        and getattr(task, "end_time", None)
        and task.end_time.date() >= week_start
    )
    completed_month = sum(
        1 for task in tasks
        if getattr(task, "status", "") == "Completed"
        and getattr(task, "end_time", None)
        and task.end_time.date() >= month_start
    )

    avg_habit_pct = int(sum(item["percentage"] for item in habit_summaries) / len(habit_summaries)) if habit_summaries else 0
    progress = []
    for goal in goals:
        if goal.period == "Daily":
            current = completed_today
        elif goal.period == "Weekly":
            current = max(completed_week, avg_habit_pct // 20)
        else:
            current = max(completed_month, avg_habit_pct // 10)

        pct = int(min(100, (current / max(goal.target_value, 1)) * 100))
        progress.append({
            "goal": goal,
            "current": current,
            "percentage": pct,
        })

    return progress


def compute_gamification(tasks, habit_summaries):
    completed_tasks = sum(1 for task in tasks if getattr(task, "status", "") == "Completed")
    habit_points = sum(item["streak"] * 2 for item in habit_summaries)
    points = completed_tasks * 10 + habit_points

    longest_habit_streak = max((item["streak"] for item in habit_summaries), default=0)
    productivity_streak = sum(1 for item in habit_summaries if item["completed_today"])

    badges = []
    if completed_tasks >= 5:
        badges.append("Task Finisher")
    if longest_habit_streak >= 5:
        badges.append("Consistency Builder")
    if points >= 100:
        badges.append("Momentum 100")
    if not badges:
        badges.append("Getting Started")

    return {
        "points": points,
        "productivity_streak": productivity_streak,
        "badges": badges,
    }


def weekly_reflection(tasks, logs, habit_summaries):
    total = len(tasks)
    completed = sum(1 for task in tasks if getattr(task, "status", "") == "Completed")
    completion_rate = int((completed / total) * 100) if total else 0
    best_day = most_productive_day(logs)
    avg_habit = int(sum(item["percentage"] for item in habit_summaries) / len(habit_summaries)) if habit_summaries else 0

    lines = [
        f"You completed {completion_rate}% of tasks this week.",
        f"{best_day} was your most productive day.",
    ]

    if avg_habit:
        lines.append(f"Your habits stayed {avg_habit}% consistent this week.")

    hard_task_hint = any((getattr(task, "estimated_time", 1.0) or 1.0) >= 3 for task in tasks)
    if hard_task_hint:
        lines.append("Try scheduling difficult tasks in the morning for a better completion rate.")
    else:
        lines.append("Keep protecting your best focus hours for the work that matters most.")

    return lines


def next_occurrence(day_of_week, hour_of_day):
    today = datetime.utcnow()
    days_ahead = (day_of_week - today.weekday()) % 7
    target = datetime.combine(today.date() + timedelta(days=days_ahead), time(hour_of_day, 0))
    if target <= today:
        target += timedelta(days=7)
    return target
