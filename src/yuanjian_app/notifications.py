"""Throttled local notification center with an optional Windows toast."""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timedelta, timezone


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _windows_notifier(title, body):
    script = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $template.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($template.CreateTextNode($args[0])) > $null
$nodes.Item(1).AppendChild($template.CreateTextNode($args[1])) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('远见').Show($toast)
"""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
            str(title),
            str(body),
        ],
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("windows_toast_failed")


class NotificationService:
    def __init__(self, database, notifier=None, now=None):
        self.database = database
        self.notifier = notifier or _windows_notifier
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _metadata(row):
        try:
            value = json.loads(row["reason"])
        except (TypeError, json.JSONDecodeError):
            return {"summary": row["reason"], "action_window_hours": None}
        return value if isinstance(value, dict) else {"summary": str(value)}

    def _recent(self, cluster_id, now):
        cutoff = _iso(now - timedelta(hours=6))
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM notification_log
                WHERE cluster_id=? AND created_at>=?
                ORDER BY created_at DESC,notification_id DESC LIMIT 1
                """,
                (cluster_id, cutoff),
            ).fetchone()

    def consider(self, impact: dict, reason: str) -> dict:
        level = str(impact.get("alert_level", "L1"))
        if level not in {"L1", "L2", "L3", "L4"}:
            raise ValueError("通知等级无效")
        if level == "L1":
            return {"status": "ignored", "delivery": "none"}
        now = self.now().astimezone(timezone.utc)
        cluster_id = str(impact.get("cluster_id", ""))
        if not cluster_id:
            raise ValueError("通知缺少事件簇")
        evidence_hash = str(impact.get("evidence_hash", ""))
        window = impact.get("action_window_hours")
        window = None if window is None else max(0, int(window))
        recent = self._recent(cluster_id, now)
        if recent is not None:
            previous = self._metadata(recent)
            previous_window = previous.get("action_window_hours")
            level_up = int(level[1:]) > int(recent["alert_level"][1:])
            evidence_changed = evidence_hash != recent["evidence_hash"]
            window_shorter = (
                window is not None
                and previous_window is not None
                and window < int(previous_window)
            )
            if not (level_up or evidence_changed or window_shorter):
                return {"status": "suppressed", "delivery": "none"}

        error_message = ""
        if level == "L2":
            delivery = "daily_digest"
            status = "digest"
        elif level == "L3":
            delivery = "local_only"
            status = "unread"
        else:
            status = "unread"
            try:
                self.notifier(
                    "远见：高优先级事件",
                    "发现一项需要立即查看的外部事件，请打开远见查看证据和行动窗口。",
                )
                delivery = "windows"
            except Exception as error:
                delivery = "local_only"
                error_message = type(error).__name__

        notification_id = "D-" + uuid.uuid4().hex
        metadata = json.dumps(
            {
                "summary": " ".join(str(reason or "").split()),
                "action_window_hours": window,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_log(
                    notification_id,cluster_id,impact_id,created_at,alert_level,
                    reason,evidence_hash,status,delivery,error_message
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    notification_id,
                    cluster_id,
                    impact.get("impact_id"),
                    _iso(now),
                    level,
                    metadata,
                    evidence_hash,
                    status,
                    delivery,
                    error_message,
                ),
            )
        return {
            "notification_id": notification_id,
            "status": "created",
            "delivery": delivery,
        }

    def list_page(self, limit: int = 20, offset: int = 0, status: str = "") -> dict:
        limit = int(limit)
        offset = int(offset)
        status = str(status or "").strip().casefold()
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("分页参数无效")
        if status not in {"", "unread", "read", "digest"}:
            raise ValueError("通知状态无效")
        where = " WHERE status=?" if status else ""
        values = [status] if status else []
        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM notification_log{where}", values
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM notification_log
                {where}
                ORDER BY created_at DESC,notification_id DESC LIMIT ? OFFSET ?
                """,
                (*values, limit, offset),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            metadata = self._metadata(row)
            item["reason"] = metadata.get("summary", "")
            item["action_window_hours"] = metadata.get("action_window_hours")
            output.append(item)
        return {"items": output, "total": total, "limit": limit, "offset": offset}

    def list_notifications(self, limit: int = 100) -> list[dict]:
        safe_limit = max(1, min(int(limit), 100))
        return self.list_page(limit=safe_limit)["items"]

    def mark_read(self, notification_id: str) -> dict:
        now = _iso(self.now())
        with self.database.connect() as connection:
            result = connection.execute(
                """
                UPDATE notification_log SET status='read',read_at=?
                WHERE notification_id=?
                """,
                (now, notification_id),
            )
            if result.rowcount != 1:
                raise KeyError(notification_id)
        return {"notification_id": notification_id, "status": "read"}

    def mark_all_read(self) -> dict:
        now = _iso(self.now())
        with self.database.connect() as connection:
            result = connection.execute(
                """
                UPDATE notification_log SET status='read',read_at=?
                WHERE status='unread'
                """,
                (now,),
            )
        return {"status": "read", "updated": result.rowcount}
