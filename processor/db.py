import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from models import Message


DB_PATH = Path("/app/data/notifications.db")


def init_db():
    """Initialize SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def log_notification(msg: Message) -> int:
    """Log notification to database, return ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """
        INSERT INTO notifications (app, title, body, timestamp, action, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (msg.app, msg.title, msg.body, msg.timestamp.isoformat(), msg.action, msg.reason),
    )
    notification_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notification_id


def update_notification(notification_id: int, action: str, reason: str):
    """Update notification status after processing."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE notifications SET action = ?, reason = ? WHERE id = ?",
        (action, reason, notification_id),
    )
    conn.commit()
    conn.close()


def check_db() -> bool:
    """Health check for database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


def get_recent_notifications(limit: int = 50) -> list[dict]:
    """Get recent notifications."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT id, app, title, body, timestamp, action, reason, feedback, created_at
        FROM notifications
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_last_notification_time(exclude_apps: set = None) -> str | None:
    """Get timestamp of most recent notification, excluding specified apps."""
    conn = sqlite3.connect(DB_PATH)
    if exclude_apps:
        placeholders = ','.join('?' * len(exclude_apps))
        cursor = conn.execute(
            f"SELECT created_at FROM notifications WHERE app NOT IN ({placeholders}) ORDER BY id DESC LIMIT 1",
            tuple(exclude_apps),
        )
    else:
        cursor = conn.execute("SELECT created_at FROM notifications ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_stats() -> dict:
    """Get notification statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN action = 'dropped' THEN 1 ELSE 0 END) as dropped,
            SUM(CASE WHEN action = 'rate_limited' THEN 1 ELSE 0 END) as rate_limited
        FROM notifications
    """)
    row = cursor.fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "sent": row[1] or 0,
        "dropped": row[2] or 0,
        "rate_limited": row[3] or 0,
    }


def get_stats_by_app() -> list[dict]:
    """Get notification statistics grouped by app."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            app,
            COUNT(*) as total,
            SUM(CASE WHEN action = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN action = 'dropped' THEN 1 ELSE 0 END) as dropped
        FROM notifications
        GROUP BY app
        ORDER BY total DESC
    """)
    rows = [{"app": r[0], "total": r[1], "sent": r[2], "dropped": r[3]} for r in cursor.fetchall()]
    conn.close()
    return rows


def set_feedback(notification_id: int, feedback: str):
    """Set feedback (good/bad) for a notification."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE notifications SET feedback = ? WHERE id = ?",
        (feedback, notification_id),
    )
    conn.commit()
    conn.close()


def migrate_db():
    """Run database migrations."""
    conn = sqlite3.connect(DB_PATH)
    # Add feedback column if it doesn't exist
    try:
        conn.execute("ALTER TABLE notifications ADD COLUMN feedback TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create dismissed_suggestions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dismissed_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT NOT NULL,
            pattern TEXT NOT NULL,
            suggestion_type TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(app, pattern, suggestion_type)
        )
    """)
    conn.commit()
    conn.close()


def dismiss_suggestion(app: str, pattern: str, suggestion_type: str):
    """Dismiss a suggestion so it won't appear again."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT OR IGNORE INTO dismissed_suggestions (app, pattern, suggestion_type)
        VALUES (?, ?, ?)
        """,
        (app, pattern, suggestion_type),
    )
    conn.commit()
    conn.close()


def get_dismissed_suggestions() -> set:
    """Get set of dismissed suggestion keys (app:pattern:type)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT app, pattern, suggestion_type FROM dismissed_suggestions")
    dismissed = {f"{r[0]}:{r[1]}:{r[2]}" for r in cursor.fetchall()}
    conn.close()
    return dismissed


def clear_feedback(notification_id: int):
    """Clear feedback for a notification (used when dismissing)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE notifications SET feedback = NULL WHERE id = ?",
        (notification_id,),
    )
    conn.commit()
    conn.close()


def get_feedback_data_for_ai() -> list[dict]:
    """Get all feedback data for AI analysis."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT app, title, body, action, feedback, reason
        FROM notifications
        WHERE feedback IS NOT NULL
        ORDER BY id DESC
        LIMIT 100
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_feedback_insights() -> dict:
    """Analyze feedback patterns to suggest rule improvements."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get dismissed suggestions to filter them out
    dismissed = get_dismissed_suggestions()

    insights = {
        "bad_sends": [],      # Sent but marked incorrect → should drop
        "bad_drops": [],      # Dropped but marked incorrect → should send
        "suggestions": [],    # Generated rule suggestions
    }

    # Find sent notifications marked as bad (too permissive)
    cursor = conn.execute("""
        SELECT app, title, body, reason, COUNT(*) as count
        FROM notifications
        WHERE action = 'sent' AND feedback = 'bad'
        GROUP BY app, title
        ORDER BY count DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        key = f"{row['app']}:{row['title']}:drop"
        if key not in dismissed:
            insights["bad_sends"].append({
                "app": row["app"],
                "title": row["title"],
                "body": row["body"][:100] if row["body"] else "",
                "reason": row["reason"],
                "count": row["count"],
            })

    # Find dropped notifications marked as incorrect (should have been sent)
    cursor = conn.execute("""
        SELECT app, title, body, reason, COUNT(*) as count
        FROM notifications
        WHERE action = 'dropped' AND feedback = 'bad'
        GROUP BY app, title
        ORDER BY count DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        key = f"{row['app']}:{row['title']}:send"
        if key not in dismissed:
            insights["bad_drops"].append({
                "app": row["app"],
                "title": row["title"],
                "body": row["body"][:100] if row["body"] else "",
                "reason": row["reason"],
                "count": row["count"],
            })

    # Analyze patterns for bad sends by sender
    cursor = conn.execute("""
        SELECT app, title, COUNT(*) as total,
               SUM(CASE WHEN feedback = 'bad' THEN 1 ELSE 0 END) as bad_count
        FROM notifications
        WHERE action = 'sent' AND feedback IS NOT NULL
        GROUP BY app, title
        HAVING bad_count >= 2 AND bad_count * 1.0 / total >= 0.5
        ORDER BY bad_count DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        key = f"{row['app']}:{row['title']}:drop"
        if key not in dismissed:
            insights["suggestions"].append({
                "type": "drop",
                "app": row["app"],
                "pattern": row["title"],
                "reason": f"Marked incorrect {row['bad_count']}/{row['total']} times",
                "rule": f'- sender_contains: "{row["title"]}"\n  action: drop',
            })

    # Analyze patterns for incorrectly dropped by sender
    cursor = conn.execute("""
        SELECT app, title, COUNT(*) as total,
               SUM(CASE WHEN feedback = 'bad' THEN 1 ELSE 0 END) as bad_count
        FROM notifications
        WHERE action = 'dropped' AND feedback IS NOT NULL
        GROUP BY app, title
        HAVING bad_count >= 2 AND bad_count * 1.0 / total >= 0.5
        ORDER BY bad_count DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        key = f"{row['app']}:{row['title']}:send"
        if key not in dismissed:
            insights["suggestions"].append({
                "type": "send",
                "app": row["app"],
                "pattern": row["title"],
                "reason": f"Marked incorrect {row['bad_count']}/{row['total']} times",
                "rule": f'- sender_contains: "{row["title"]}"\n  action: send',
            })

    # Get feedback stats
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total_feedback,
            SUM(CASE WHEN feedback = 'bad' THEN 1 ELSE 0 END) as bad
        FROM notifications
        WHERE feedback IS NOT NULL
    """)
    row = cursor.fetchone()
    insights["stats"] = {
        "total_feedback": row["total_feedback"] or 0,
        "bad": row["bad"] or 0,
    }

    conn.close()
    return insights
