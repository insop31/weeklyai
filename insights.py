from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
import json
import logging
import os
import random
from urllib import error, request

from config import load_environment


load_environment()
logger = logging.getLogger(__name__)
_quest_cache = {}


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


def build_user_notifications(tasks, logs, habits, habit_entries, goals, calendar_events, user_name=None, now=None):
    now = now or datetime.utcnow()
    today = now.date()
    habit_summaries = summarize_habits(habits, habit_entries)
    goal_progress = compute_goal_progress(goals, tasks, habit_summaries)

    notifications = []
    notifications.extend(_build_task_notifications(tasks, now))
    notifications.extend(_build_habit_notifications(habits, habit_entries, habit_summaries, today))
    notifications.extend(_build_goal_notifications(goal_progress, today))
    notifications.extend(_build_event_notifications(calendar_events, today))

    notifications.sort(
        key=lambda item: (
            _notification_rank(item["severity"]),
            item.get("sort_at") or datetime.max,
            item.get("title", ""),
        )
    )

    return notifications[:18]


def compute_gamification(tasks, habit_summaries, user_name=None):
    completed_tasks = sum(1 for task in tasks if getattr(task, "status", "") == "Completed")
    habit_points = sum(item["streak"] * 2 for item in habit_summaries)
    points = completed_tasks * 10 + habit_points
    unique_active_tasks = []
    seen_titles = set()
    for task in sorted(
        [t for t in tasks if getattr(t, "status", "") in {"Pending", "In Progress", "Missed"}],
        key=lambda t: (-compute_priority_score(t), getattr(t, "deadline", None) or getattr(t, "start_time", None) or getattr(t, "created_at", datetime.utcnow()))
    ):
        title = getattr(task, "title", "Task").strip().lower()
        if title not in seen_titles:
            seen_titles.add(title)
            unique_active_tasks.append(task)
            if len(unique_active_tasks) >= 5:
                break
    active_tasks = unique_active_tasks

    longest_habit_streak = max((item["streak"] for item in habit_summaries), default=0)
    productivity_streak = sum(1 for item in habit_summaries if item["completed_today"])

    level_steps = [0, 40, 90, 150, 220, 300, 390, 490, 600, 720]
    leagues = [
        {"name": "Rookie League", "min_points": 0, "icon": "R", "accent": "purple"},
        {"name": "Challenger League", "min_points": 80, "icon": "C", "accent": "lime"},
        {"name": "Elite League", "min_points": 180, "icon": "E", "accent": "purple"},
        {"name": "Champion League", "min_points": 320, "icon": "M", "accent": "lime"},
        {"name": "Legend League", "min_points": 520, "icon": "L", "accent": "purple"},
    ]

    current_level = 1
    for index, threshold in enumerate(level_steps, start=1):
        if points >= threshold:
            current_level = index
        else:
            break

    current_floor = level_steps[current_level - 1]
    next_level_points = level_steps[current_level] if current_level < len(level_steps) else None
    if next_level_points is None:
        level_progress = 100
    else:
        span = max(next_level_points - current_floor, 1)
        level_progress = int(min(100, ((points - current_floor) / span) * 100))

    league = leagues[0]
    for candidate in leagues:
        if points >= candidate["min_points"]:
            league = candidate
        else:
            break

    unlocked_features = [
        {"name": "Quick Wins", "description": "Complete tasks to stack XP.", "level": 1, "unlocked": current_level >= 1},
        {"name": "Badge Cabinet", "description": "Show off earned milestones.", "level": 2, "unlocked": current_level >= 2},
        {"name": "Focus Zones", "description": "League promotion unlocks stronger status.", "level": 3, "unlocked": current_level >= 3},
        {"name": "Streak Shield", "description": "Habit consistency powers bonus XP.", "level": 4, "unlocked": current_level >= 4},
        {"name": "Master Quest", "description": "High ranks unlock long-run goals.", "level": 6, "unlocked": current_level >= 6},
    ]

    next_unlock = next((item for item in unlocked_features if not item["unlocked"]), None)

    badge_rules = [
        {
            "name": "Task Finisher",
            "description": "Finish 5 tasks",
            "earned": completed_tasks >= 5,
            "progress": min(completed_tasks, 5),
            "target": 5,
        },
        {
            "name": "Consistency Builder",
            "description": "Reach a 5-day habit streak",
            "earned": longest_habit_streak >= 5,
            "progress": min(longest_habit_streak, 5),
            "target": 5,
        },
        {
            "name": "Momentum 100",
            "description": "Earn 100 XP",
            "earned": points >= 100,
            "progress": min(points, 100),
            "target": 100,
        },
        {
            "name": "League Climber",
            "description": "Enter Challenger League",
            "earned": points >= 80,
            "progress": min(points, 80),
            "target": 80,
        },
        {
            "name": "Daily Grinder",
            "description": "Complete 3 habits in one day",
            "earned": productivity_streak >= 3,
            "progress": min(productivity_streak, 3),
            "target": 3,
        },
    ]

    badges = [badge["name"] for badge in badge_rules if badge["earned"]]
    if not badges:
        badges.append("Getting Started")

    ai_quests = generate_game_quests(tasks, habit_summaries, user_name=user_name)

    return {
        "points": points,
        "productivity_streak": productivity_streak,
        "badges": badges,
        "badge_details": badge_rules,
        "active_tasks": [
            {
                "id": getattr(task, "id", None),
                "title": getattr(task, "title", "Task"),
                "category": getattr(task, "category", "Work") or "Work",
                "score": compute_priority_score(task),
                "status": getattr(task, "status", "Pending") or "Pending",
            }
            for task in active_tasks
        ] + ai_quests,
        "completed_tasks": completed_tasks,
        "longest_habit_streak": longest_habit_streak,
        "level": current_level,
        "level_progress": level_progress,
        "level_floor": current_floor,
        "next_level_points": next_level_points,
        "points_to_next_level": max((next_level_points or points) - points, 0) if next_level_points else 0,
        "league": league,
        "unlocked_features": unlocked_features,
        "next_unlock": next_unlock,
    }


def generate_game_quests(tasks, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    cache_key = _build_game_quest_cache_key(tasks, habit_summaries, user_name=user_name, now=now)
    if cache_key in _quest_cache:
        return _quest_cache[cache_key]

    quests = _generate_ai_game_quests(tasks, habit_summaries, user_name=user_name, now=now)
    if quests is None:
        quests = _fallback_game_quests(tasks, habit_summaries)

    _quest_cache[cache_key] = quests
    return quests


def _build_game_quest_cache_key(tasks, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    task_signature = tuple(
        (
            getattr(task, "title", "Task"),
            getattr(task, "status", "Pending"),
            getattr(task, "priority", "Medium"),
            getattr(task, "category", "Work"),
        )
        for task in sorted(
            tasks,
            key=lambda task: (
                getattr(task, "status", ""),
                getattr(task, "deadline", None) or getattr(task, "start_time", None) or getattr(task, "created_at", datetime.utcnow()),
                getattr(task, "title", ""),
            ),
        )[:10]
    )
    habit_signature = tuple(
        (
            getattr(item["habit"], "title", "Habit"),
            item.get("streak", 0),
            item.get("percentage", 0),
            item.get("completed_today", False),
        )
        for item in habit_summaries[:6]
    )
    return (user_name or "", now.date().isoformat(), task_signature, habit_signature)


def _fallback_game_quests(tasks, habit_summaries):
    quests = []
    pending_tasks = [
        task for task in tasks
        if getattr(task, "status", "") in {"Pending", "In Progress", "Missed"}
    ]
    top_task = max(pending_tasks, key=compute_priority_score, default=None)
    strongest_habit = max(habit_summaries, key=lambda item: item["streak"], default=None)
    lowest_habit = min(habit_summaries, key=lambda item: item["percentage"], default=None) if habit_summaries else None

    if top_task:
        quests.append({
            "id": f"ai-quest-focus-{getattr(top_task, 'id', 'task')}",
            "title": f"Boss battle: finish {getattr(top_task, 'title', 'your top task')}",
            "category": "AI Quest",
            "score": min(99, compute_priority_score(top_task) + 8),
            "status": "Bonus Quest",
        })

    if strongest_habit and strongest_habit["streak"] > 0:
        quests.append({
            "id": f"ai-quest-streak-{getattr(strongest_habit['habit'], 'id', 'habit')}",
            "title": f"Protect your {strongest_habit['habit'].title} streak today",
            "category": "Habit Quest",
            "score": 72,
            "status": "Streak Quest",
        })

    if lowest_habit and not lowest_habit["completed_today"]:
        quests.append({
            "id": f"ai-quest-revive-{getattr(lowest_habit['habit'], 'id', 'habit')}",
            "title": f"Revive {lowest_habit['habit'].title} with one easy check-in",
            "category": "Habit Quest",
            "score": 61,
            "status": "Recovery Quest",
        })

    return quests[:3]


def build_recent_completion_feed(tasks, logs, limit=5):
    task_map = {
        task.id: task for task in tasks
        if getattr(task, "id", None) is not None and getattr(task, "status", "") == "Completed"
    }
    feed = []
    seen_task_ids = set()

    ordered_logs = sorted(
        [log for log in logs if getattr(log, "completion_time", None)],
        key=lambda log: log.completion_time,
        reverse=True,
    )

    for log in ordered_logs:
        task = task_map.get(getattr(log, "task_id", None))
        if not task or task.id in seen_task_ids:
            continue
        seen_task_ids.add(task.id)
        feed.append({
            "id": task.id,
            "title": getattr(task, "title", "Completed task"),
            "category": getattr(task, "category", "Work") or "Work",
            "xp": 10,
            "completed_at": log.completion_time.isoformat(),
        })
        if len(feed) >= limit:
            break

    return feed


def weekly_reflection(tasks, logs, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    ai_reflection = _generate_ai_weekly_reflection(
        tasks, logs, habit_summaries, user_name=user_name, now=now
    )
    if ai_reflection:
        logger.info("Weekly reflection generated via AI.")
        return ai_reflection
    logger.info("Weekly reflection fell back to local summary.")
    return _fallback_weekly_reflection(tasks, logs, habit_summaries)


def _fallback_weekly_reflection(tasks, logs, habit_summaries):
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


def _generate_ai_weekly_reflection(tasks, logs, habit_summaries, user_name=None, now=None):
    settings = _resolve_ai_settings()
    if not settings:
        logger.info("Weekly reflection AI disabled: no provider settings found.")
        return None

    now = now or datetime.utcnow()
    logger.info(
        "Weekly reflection requesting AI provider=%s model=%s base_url=%s",
        settings["provider"],
        settings["model"],
        settings["base_url"],
    )
    creative_direction = random.choice([
        "encouraging and grounded",
        "clear and insightful",
        "warm and strategic",
        "steady and motivating",
    ])

    context = _build_weekly_reflection_context(
        tasks, logs, habit_summaries, user_name=user_name, now=now
    )
    payload = {
        "model": settings["model"],
        "input": [
            {
                "role": "system",
                "content": (
                    "You write short weekly reflection summaries for a productivity dashboard. "
                    "Keep the tone warm, specific, and practical. "
                    "Respond with valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a weekly reflection in a {creative_direction} tone.\n"
                    "Return JSON with exactly one key: lines.\n"
                    "Constraints:\n"
                    "- lines must be an array of 3 or 4 strings.\n"
                    "- Each line should be under 140 characters.\n"
                    "- Include one performance insight, one habit insight, and one practical next-step suggestion.\n"
                    "- Mention the most important bottleneck or priority shift from the data.\n"
                    "- Keep each line concrete and focused, not generic encouragement.\n"
                    "- Avoid markdown, emojis, hashtags, and quotation marks.\n"
                    "- Make the reflection feel specific to this week's data.\n\n"
                    f"{context}\n"
                    f"Variation seed: {random.randint(1000, 999999)}"
                ),
            },
        ],
        "temperature": 0.9,
        "max_output_tokens": 220,
    }

    req = request.Request(
        f"{settings['base_url']}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_ai_headers(settings["api_key"], settings["provider"]),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        logger.warning("Weekly reflection AI request failed with HTTP %s", exc.code)
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Weekly reflection AI request failed: %s", exc)
        return None

    parsed = _extract_response_text(data)
    if not parsed:
        return None

    try:
        content = json.loads(parsed)
    except json.JSONDecodeError:
        return None

    lines = content.get("lines")
    if not isinstance(lines, list):
        return None

    cleaned_lines = []
    for line in lines[:4]:
        if not isinstance(line, str):
            continue
        cleaned = " ".join(line.split()).strip()[:140]
        if cleaned:
            cleaned_lines.append(cleaned)

    if len(cleaned_lines) < 3:
        return None

    logger.info(
        "Weekly reflection AI response accepted with provider=%s lines=%s",
        settings["provider"],
        len(cleaned_lines),
    )
    return cleaned_lines


def _generate_ai_game_quests(tasks, habit_summaries, user_name=None, now=None):
    settings = _resolve_ai_settings()
    if not settings:
        logger.info("Game quests AI disabled: no provider settings found.")
        return None

    now = now or datetime.utcnow()
    logger.info(
        "Game quests requesting AI provider=%s model=%s base_url=%s",
        settings["provider"],
        settings["model"],
        settings["base_url"],
    )
    context = _build_game_quest_context(tasks, habit_summaries, user_name=user_name, now=now)
    payload = {
        "model": settings["model"],
        "input": [
            {
                "role": "system",
                "content": (
                    "You create short gamified productivity quests for a planner dashboard. "
                    "The quests should feel playful, specific, and actionable. "
                    "Respond with valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with exactly one key: quests.\n"
                    "quests must be an array of 3 objects.\n"
                    "Each object must have exactly these keys: title, category, score, status.\n"
                    "Constraints:\n"
                    "- title: under 70 characters and tied to the user's actual tasks or habits.\n"
                    "- category: 1 to 3 words.\n"
                    "- score: integer from 40 to 99.\n"
                    "- status: 1 to 3 words like Bonus Quest or Boss Fight.\n"
                    "- Make them feel like game quests, not generic todos.\n"
                    "- Avoid markdown, emojis, quotation marks inside fields, and fantasy nonsense.\n\n"
                    f"{context}\n"
                    f"Variation seed: {random.randint(1000, 999999)}"
                ),
            },
        ],
        "temperature": 0.9,
        "max_output_tokens": 260,
    }

    req = request.Request(
        f"{settings['base_url']}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_ai_headers(settings["api_key"], settings["provider"]),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        logger.warning("Game quests AI request failed with HTTP %s", exc.code)
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Game quests AI request failed: %s", exc)
        return None

    parsed = _extract_response_text(data)
    if not parsed:
        return None

    try:
        content = json.loads(parsed)
    except json.JSONDecodeError:
        return None

    quests = content.get("quests")
    if not isinstance(quests, list):
        return None

    cleaned_quests = []
    for index, quest in enumerate(quests[:3], start=1):
        if not isinstance(quest, dict):
            continue
        title = " ".join(str(quest.get("title", "")).split()).strip()[:70]
        category = " ".join(str(quest.get("category", "")).split()).strip()[:20]
        status = " ".join(str(quest.get("status", "")).split()).strip()[:24]
        try:
            score = int(quest.get("score", 60))
        except (TypeError, ValueError):
            score = 60
        score = max(40, min(99, score))

        if not title or not category or not status:
            continue

        cleaned_quests.append({
            "id": f"ai-quest-{index}",
            "title": title,
            "category": category,
            "score": score,
            "status": status,
        })

    if len(cleaned_quests) < 2:
        return None

    logger.info(
        "Game quests AI response accepted with provider=%s quests=%s",
        settings["provider"],
        len(cleaned_quests),
    )
    return cleaned_quests


def generate_daily_intention(tasks, logs, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    ai_intention = _generate_ai_daily_intention(tasks, logs, habit_summaries, user_name=user_name, now=now)
    if ai_intention:
        return ai_intention
    return _fallback_daily_intention(tasks, logs, habit_summaries, user_name=user_name, now=now)


def _fallback_daily_intention(tasks, logs, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    pending_tasks = [task for task in tasks if getattr(task, "status", "") != "Completed"]
    completed_tasks = [task for task in tasks if getattr(task, "status", "") == "Completed"]
    top_task = max(pending_tasks, key=compute_priority_score, default=None)
    strongest_habit = max(habit_summaries, key=lambda item: item["streak"], default=None)
    productive_day = most_productive_day(logs)

    focus_options = [
        "Gentle Productivity",
        "Calm Momentum",
        "Quiet Progress",
        "Focused Energy",
        "Steady Clarity",
        "Intentional Action",
    ]
    creative_angles = [
        "small wins",
        "clear priorities",
        "kind focus",
        "steady effort",
        "one meaningful move",
        "calm consistency",
    ]

    angle = random.choice(creative_angles)
    focus = random.choice(focus_options)
    greeting_name = (user_name or "there").split(" ")[0]

    if top_task and strongest_habit:
        title = f"Lead with {angle} today."
        body = (
            f"{greeting_name}, begin with {top_task.title} and let your {strongest_habit['habit'].title.lower()} streak "
            f"set the tone for the rest of the day."
        )
    elif top_task:
        title = f"Give your best hour to {angle}."
        body = f"{greeting_name}, start with {top_task.title} before the day gets noisy, then build around that win."
    elif strongest_habit:
        title = f"Protect your {angle}."
        body = (
            f"Your {strongest_habit['habit'].title.lower()} habit is already creating momentum. "
            f"Use it as the anchor for today."
        )
    elif completed_tasks:
        title = f"Build on yesterday's {angle}."
        body = "You already have proof you can finish strong. Pick one clear next step and let that be enough for now."
    else:
        title = f"Make space for {angle}."
        body = "Choose one task that matters, define what done looks like, and move through it with less pressure."

    if productive_day != "No clear pattern yet":
        body = f"{body} {productive_day} has been a strong day for you, so lean into that rhythm."

    return {
        "badge": "Daily Intention",
        "focus": focus,
        "title": title,
        "body": body,
        "action": "Refresh intention",
        "source": "fallback",
        "generated_at": now.isoformat(),
    }


def _generate_ai_daily_intention(tasks, logs, habit_summaries, user_name=None, now=None):
    settings = _resolve_ai_settings()
    if not settings:
        return None

    now = now or datetime.utcnow()
    creative_direction = random.choice([
        "gentle and reflective",
        "calm and motivating",
        "softly ambitious",
        "warm and grounded",
        "hopeful and steady",
    ])

    context = _build_intention_context(tasks, logs, habit_summaries, user_name=user_name, now=now)
    payload = {
        "model": settings["model"],
        "input": [
            {
                "role": "system",
                "content": (
                    "You write short daily intention cards for a productivity dashboard. "
                    "Keep the tone warm, clear, and emotionally intelligent. "
                    "Respond with valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a fresh daily intention in a {creative_direction} tone.\n"
                    "Return JSON with exactly these keys: badge, focus, title, body, action.\n"
                    "Constraints:\n"
                    "- badge: 2 to 4 words.\n"
                    "- focus: 2 to 4 words.\n"
                    "- title: under 70 characters.\n"
                    "- body: 1 or 2 sentences, under 220 characters.\n"
                    "- action: 2 to 4 words.\n"
                    "- Avoid hashtags, markdown, emojis, and quotation marks.\n"
                    "- Make it feel unique for this request.\n\n"
                    f"{context}\n"
                    f"Variation seed: {random.randint(1000, 999999)}"
                ),
            },
        ],
        "temperature": 1,
        "max_output_tokens": 180,
    }

    req = request.Request(
        f"{settings['base_url']}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_ai_headers(settings["api_key"], settings["provider"]),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        logger.warning("Daily intention AI request failed with HTTP %s", exc.code)
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Daily intention AI request failed: %s", exc)
        return None

    parsed = _extract_response_text(data)
    if not parsed:
        return None

    try:
        content = json.loads(parsed)
    except json.JSONDecodeError:
        return None

    required_fields = {"badge", "focus", "title", "body", "action"}
    if not required_fields.issubset(content):
        return None

    return {
        "badge": str(content["badge"]).strip()[:40] or "Daily Intention",
        "focus": str(content["focus"]).strip()[:40] or "Gentle Productivity",
        "title": str(content["title"]).strip()[:80],
        "body": str(content["body"]).strip()[:240],
        "action": str(content["action"]).strip()[:40] or "Refresh intention",
        "source": "ai",
        "generated_at": now.isoformat(),
    }


def _build_intention_context(tasks, logs, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    pending_tasks = [task for task in tasks if getattr(task, "status", "") != "Completed"]
    top_tasks = sorted(pending_tasks, key=compute_priority_score, reverse=True)[:3]
    habit_lines = [
        f"{item['habit'].title} ({item['streak']} day streak, {item['percentage']}% this week)"
        for item in habit_summaries[:3]
    ]
    recent_wins = [
        getattr(task, "title", "Task")
        for task in tasks
        if getattr(task, "status", "") == "Completed"
    ][:3]

    return "\n".join([
        f"User: {user_name or 'Planner user'}",
        f"Today: {now.strftime('%A, %B %d')}",
        f"Pending task count: {len(pending_tasks)}",
        "Top pending tasks: " + (", ".join(getattr(task, "title", "Task") for task in top_tasks) or "None"),
        "Recent completed tasks: " + (", ".join(recent_wins) or "None"),
        "Habit momentum: " + (", ".join(habit_lines) or "None"),
        f"Most productive day: {most_productive_day(logs)}",
    ])


def _build_weekly_reflection_context(tasks, logs, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    total = len(tasks)
    completed_tasks = [task for task in tasks if getattr(task, "status", "") == "Completed"]
    pending_tasks = [task for task in tasks if getattr(task, "status", "") != "Completed"]
    completion_rate = int((len(completed_tasks) / total) * 100) if total else 0
    avg_habit = int(sum(item["percentage"] for item in habit_summaries) / len(habit_summaries)) if habit_summaries else 0
    strongest_habit = max(habit_summaries, key=lambda item: item["streak"], default=None)
    top_pending = sorted(pending_tasks, key=compute_priority_score, reverse=True)[:3]
    recent_wins = build_recent_completion_feed(tasks, logs, limit=3)

    return "\n".join([
        f"User: {user_name or 'Planner user'}",
        f"Week ending: {now.strftime('%A, %B %d')}",
        f"Total tasks: {total}",
        f"Completed tasks: {len(completed_tasks)}",
        f"Completion rate: {completion_rate}%",
        "Recent wins: " + (", ".join(item["title"] for item in recent_wins) or "None"),
        "Top pending tasks: " + (", ".join(getattr(task, "title", "Task") for task in top_pending) or "None"),
        f"Most productive day: {most_productive_day(logs)}",
        f"Average habit consistency: {avg_habit}%",
        "Strongest habit: " + (
            f"{strongest_habit['habit'].title} ({strongest_habit['streak']} day streak)"
            if strongest_habit else "None"
        ),
    ])


def _build_game_quest_context(tasks, habit_summaries, user_name=None, now=None):
    now = now or datetime.utcnow()
    pending_tasks = [
        task for task in tasks
        if getattr(task, "status", "") in {"Pending", "In Progress", "Missed"}
    ]
    top_pending = sorted(pending_tasks, key=compute_priority_score, reverse=True)[:4]
    completed_count = sum(1 for task in tasks if getattr(task, "status", "") == "Completed")
    top_habits = sorted(habit_summaries, key=lambda item: (item["streak"], item["percentage"]), reverse=True)[:3]
    weak_habits = sorted(habit_summaries, key=lambda item: item["percentage"])[:2]

    return "\n".join([
        f"User: {user_name or 'Planner user'}",
        f"Today: {now.strftime('%A, %B %d')}",
        f"Completed task count: {completed_count}",
        "Top pending tasks: " + (
            ", ".join(
                f"{getattr(task, 'title', 'Task')} [{getattr(task, 'priority', 'Medium')}, score {compute_priority_score(task)}]"
                for task in top_pending
            ) or "None"
        ),
        "Strongest habits: " + (
            ", ".join(
                f"{item['habit'].title} ({item['streak']} streak, {item['percentage']}%)"
                for item in top_habits
            ) or "None"
        ),
        "Needs momentum: " + (
            ", ".join(
                f"{item['habit'].title} ({item['percentage']}%)"
                for item in weak_habits
            ) or "None"
        ),
    ])


def _extract_response_text(data):
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()

        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") != "output_text":
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return None


def _build_task_notifications(tasks, now):
    notifications = []
    pending_tasks = [
        task for task in tasks
        if getattr(task, "status", "") in {"Pending", "In Progress"}
    ]

    unique_pending_tasks = []
    seen_titles = set()
    for task in pending_tasks:
        title = getattr(task, "title", "Task").strip().lower()
        if title not in seen_titles:
            seen_titles.add(title)
            unique_pending_tasks.append(task)

    for task in unique_pending_tasks:
        due_at = getattr(task, "deadline", None)
        start_at = getattr(task, "start_time", None)

        if due_at:
            delta = due_at - now
            hours_left = delta.total_seconds() / 3600
            if hours_left <= 0:
                notifications.append(_notification(
                    kind="task",
                    severity="critical",
                    title=f"{task.title} is overdue",
                    body=f"The deadline passed {_format_relative_time(due_at, now)}. Wrap this up or reschedule it now.",
                    when_label=f"Deadline {due_at.strftime('%b %d at %I:%M %p')}",
                    meta="Pending task",
                    sort_at=due_at,
                ))
            elif hours_left <= 6:
                notifications.append(_notification(
                    kind="task",
                    severity="high",
                    title=f"Start {task.title} soon",
                    body=f"It is due {_format_relative_time(due_at, now)}. This is a strong candidate for your next work block.",
                    when_label=f"Due {due_at.strftime('%b %d at %I:%M %p')}",
                    meta="Pending task",
                    sort_at=due_at,
                ))
            elif hours_left <= 24:
                notifications.append(_notification(
                    kind="task",
                    severity="medium",
                    title=f"{task.title} is due today",
                    body=f"Keep time open for it before the deadline arrives {_format_relative_time(due_at, now)}.",
                    when_label=f"Due {due_at.strftime('%b %d at %I:%M %p')}",
                    meta="Pending task",
                    sort_at=due_at,
                ))
        elif start_at:
            delta = start_at - now
            hours_until = delta.total_seconds() / 3600
            if hours_until <= 0:
                notifications.append(_notification(
                    kind="task",
                    severity="high",
                    title=f"{task.title} should be in progress",
                    body=f"The scheduled start was {_format_relative_time(start_at, now)}. Jump in now or move it to a realistic time.",
                    when_label=f"Start time {start_at.strftime('%b %d at %I:%M %p')}",
                    meta="Scheduled task",
                    sort_at=start_at,
                ))
            elif hours_until <= 2:
                notifications.append(_notification(
                    kind="task",
                    severity="medium",
                    title=f"{task.title} starts soon",
                    body=f"Your scheduled work block begins {_format_relative_time(start_at, now)}. Get set up before it starts.",
                    when_label=f"Starts {start_at.strftime('%b %d at %I:%M %p')}",
                    meta="Scheduled task",
                    sort_at=start_at,
                ))

    return notifications


def _build_habit_notifications(habits, habit_entries, habit_summaries, today):
    notifications = []
    completed_today = {
        entry.habit_id
        for entry in habit_entries
        if getattr(entry, "completed", False) and getattr(entry, "entry_date", None) == today
    }

    for summary in habit_summaries:
        habit = summary["habit"]
        if habit.id in completed_today:
            continue

        streak = summary["streak"]
        if streak >= 3:
            body = f"You have a {streak}-day streak going. Check in today to keep that momentum alive."
            severity = "medium"
        else:
            body = "A quick check-in today keeps this habit visible and easier to repeat tomorrow."
            severity = "low"

        notifications.append(_notification(
            kind="habit",
            severity=severity,
            title=f"Remember your {habit.title} habit",
            body=body,
            when_label="Due today",
            meta=f"Habit in {habit.category}",
            sort_at=datetime.combine(today, time(20, 0)),
        ))

    return notifications


def _build_goal_notifications(goal_progress, today):
    notifications = []
    for item in goal_progress:
        goal = item["goal"]
        current = item["current"]
        target = max(getattr(goal, "target_value", 1) or 1, 1)
        remaining = max(target - current, 0)
        if remaining <= 0:
            continue

        if getattr(goal, "period", "Weekly") == "Daily":
            severity = "high"
            when_label = "Ends today"
        elif goal.period == "Weekly":
            severity = "medium"
            when_label = f"Week ends { _end_of_week(today).strftime('%b %d') }"
        else:
            severity = "low"
            when_label = f"Month ends { _end_of_month(today).strftime('%b %d') }"

        notifications.append(_notification(
            kind="goal",
            severity=severity,
            title=f"Progress needed for {goal.title}",
            body=f"You are at {current}/{target}. You still need {remaining} more to hit this {goal.period.lower()} goal.",
            when_label=when_label,
            meta=f"{goal.period} goal",
            sort_at=datetime.combine(today, time(21, 0)),
        ))

    return notifications


def _build_event_notifications(calendar_events, today):
    notifications = []
    for event in calendar_events:
        event_day = getattr(event, "event_date", None)
        if not event_day:
            continue

        days_until = (event_day - today).days
        if days_until < 0 or days_until > 3:
            continue

        if days_until == 0:
            severity = "high"
            title = f"{event.title} is today"
            body = (event.notes or "You planned this for today. Make room for it before the day fills up.")[:220]
            when_label = f"Today, {event_day.strftime('%b %d')}"
        elif days_until == 1:
            severity = "medium"
            title = f"{event.title} is tomorrow"
            body = (event.notes or "This event is coming up tomorrow, so it is worth preparing for today.")[:220]
            when_label = f"Tomorrow, {event_day.strftime('%b %d')}"
        else:
            severity = "low"
            title = f"{event.title} is coming up"
            body = (event.notes or f"This event is {days_until} days away. A little prep now will make it easier.")[:220]
            when_label = event_day.strftime('%A, %b %d')

        notifications.append(_notification(
            kind="event",
            severity=severity,
            title=title,
            body=body,
            when_label=when_label,
            meta=f"{getattr(event, 'event_type', 'Event')} event",
            sort_at=datetime.combine(event_day, time.min),
        ))

    return notifications


def _notification(kind, severity, title, body, when_label, meta, sort_at=None):
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "body": body,
        "when_label": when_label,
        "meta": meta,
        "sort_at": sort_at,
    }


def _notification_rank(severity):
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)


def _format_relative_time(target, now):
    delta_seconds = int((target - now).total_seconds())
    tense = "from now" if delta_seconds >= 0 else "ago"
    minutes = max(1, abs(delta_seconds) // 60)

    if minutes < 60:
        value = minutes
        unit = "minute"
    elif minutes < 1440:
        value = minutes // 60
        unit = "hour"
    else:
        value = minutes // 1440
        unit = "day"

    suffix = "" if value == 1 else "s"
    return f"in {value} {unit}{suffix}" if tense == "from now" else f"{value} {unit}{suffix} ago"


def _end_of_week(today):
    return today + timedelta(days=(6 - today.weekday()))


def _end_of_month(today):
    next_month = today.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def _resolve_ai_settings():
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return None

    is_openrouter = api_key.startswith("sk-or-v1-")
    provider = "openrouter" if is_openrouter else "openai"
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or "").strip()

    if not base_url:
        base_url = "https://openrouter.ai/api/v1" if is_openrouter else "https://api.openai.com/v1"

    if not model:
        model = "openai/gpt-4.1-mini" if is_openrouter else "gpt-4.1-mini"

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "provider": provider,
    }


def _build_ai_headers(api_key, provider):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_REFERER", "http://localhost")
        headers["X-Title"] = os.getenv("OPENROUTER_TITLE", "WeeklyAI")
    return headers


def next_occurrence(day_of_week, hour_of_day):
    today = datetime.utcnow()
    days_ahead = (day_of_week - today.weekday()) % 7
    target = datetime.combine(today.date() + timedelta(days=days_ahead), time(hour_of_day, 0))
    if target <= today:
        target += timedelta(days=7)
    return target
