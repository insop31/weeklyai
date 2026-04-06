import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import LabelEncoder
from insights import compute_priority_score, recommend_subtasks, suggest_reschedule_slot

# In-memory model cache per user
_model_cache = {}

def _get_features(logs_df):
    """Encode raw log rows into ML feature matrix."""
    le = LabelEncoder()
    priority_map = {"Low": 0, "Medium": 1, "High": 2}

    X = pd.DataFrame({
        "priority":       logs_df["priority"].map(priority_map).fillna(1),
        "estimated_time": logs_df["estimated_time"].fillna(1.0),
        "day_of_week":    logs_df["day_of_week"],
        "hour_of_day":    logs_df["hour_of_day"],
        "category":       le.fit_transform(logs_df["category"].fillna("Work")),
    })
    y = logs_df["completed_on_time"].astype(int)
    return X, y, le


def train_model(user_id, db, ActivityLog, Task):
    """Train LR + DT for a user if >= 10 log rows exist."""
    from sqlalchemy.orm import Session

    rows = (db.session.query(ActivityLog, Task)
            .join(Task, ActivityLog.task_id == Task.id)
            .filter(ActivityLog.user_id == user_id)
            .all())

    if len(rows) < 10:
        _model_cache[user_id] = None   # signals cold start
        return

    records = []
    for log, task in rows:
        on_time = (
            task.status == "Completed"
            and log.completion_time is not None
            and task.deadline is not None
            and log.completion_time <= task.deadline
        )
        records.append({
            "priority":          task.priority,
            "estimated_time":    task.estimated_time or 1.0,
            "day_of_week":       log.day_of_week,
            "hour_of_day":       log.hour_of_day,
            "category":          task.category or "Work",
            "completed_on_time": int(on_time),
        })

    df = pd.DataFrame(records)
    X, y, le = _get_features(df)

    lr = LogisticRegression(max_iter=300)
    lr.fit(X, y)

    dt = DecisionTreeClassifier(max_depth=4)
    dt.fit(X, y)

    _model_cache[user_id] = {"lr": lr, "dt": dt, "le": le}


def predict_completion(user_id, task_features: dict) -> float:
    """Return probability (0–1) that this task will be completed on time."""
    cache = _model_cache.get(user_id)
    if cache is None:
        # Cold-start: score by priority
        return {"High": 0.8, "Medium": 0.5, "Low": 0.3}.get(
            task_features.get("priority", "Medium"), 0.5
        )

    priority_map = {"Low": 0, "Medium": 1, "High": 2}
    le = cache["le"]
    try:
        cat_enc = le.transform([task_features.get("category", "Work")])[0]
    except ValueError:
        cat_enc = 0

    X = np.array([[
        priority_map.get(task_features.get("priority", "Medium"), 1),
        task_features.get("estimated_time", 1.0),
        task_features.get("day_of_week", 0),
        task_features.get("hour_of_day", 9),
        cat_enc,
    ]])
    prob = cache["lr"].predict_proba(X)[0][1]
    return round(float(prob), 2)


def get_productive_slots(user_id, db, ActivityLog):
    """Return top 3 (day_of_week, hour_of_day) combos with best completion rate."""
    rows = (db.session.query(ActivityLog)
            .filter(ActivityLog.user_id == user_id,
                    ActivityLog.completion_time.isnot(None))
            .all())

    if not rows:
        return [(0, 9), (1, 9), (2, 9)]  # fallback: Mon–Wed 9 AM

    from collections import defaultdict
    slot_counts = defaultdict(int)
    for r in rows:
        slot_counts[(r.day_of_week, r.hour_of_day)] += 1

    top3 = sorted(slot_counts, key=slot_counts.get, reverse=True)[:3]
    return top3


def recommend_schedule(user_id, pending_tasks, db, ActivityLog, Task):
    """Sort pending tasks by ML completion probability and flag missed ones."""
    from datetime import datetime
    slots = get_productive_slots(user_id, db, ActivityLog)

    results = []
    for task in pending_tasks:
        prob = predict_completion(user_id, {
            "priority":       task.priority,
            "estimated_time": task.estimated_time or 1.0,
            "day_of_week":    task.start_time.weekday() if task.start_time else 0,
            "hour_of_day":    task.start_time.hour if task.start_time else 9,
            "category":       task.category or "Work",
        })
        missed = (
            task.deadline is not None
            and task.deadline < datetime.utcnow()
            and task.status != "Completed"
        )
        best_slot = suggest_reschedule_slot(task, slots)
        results.append({
            "task":           task,
            "probability":    prob,
            "suggested_slot": best_slot,
            "reschedule":     missed,
            "smart_priority": compute_priority_score(task),
            "subtasks":       recommend_subtasks(task),
        })

    return sorted(results, key=lambda x: (x["smart_priority"], x["probability"]), reverse=True)
