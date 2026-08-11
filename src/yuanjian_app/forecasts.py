import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4


ALLOWED_PROBABILITIES = {0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 0.95}


class ForecastConflictError(ValueError):
    """Raised when a new forecast would reuse an existing identity."""


def parse_frontmatter(text):
    """Parse the flat YAML subset used by forecast cards."""
    fields = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fields
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    return fields


def parse_sections(text):
    """Parse the named reasoning sections from a rendered forecast card."""
    names = {
        "因果链": "causal_chain",
        "支持证据": "supporting_evidence",
        "反对证据": "opposing_evidence",
        "替代假设": "alternatives",
        "反证条件": "falsification",
        "建议行动": "recommended_action",
    }
    result = {}
    current = None
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                result[current] = "\n".join(lines).strip()
            current = names.get(line.removeprefix("## ").strip())
            lines = []
        elif current:
            lines.append(line)
    if current:
        result[current] = "\n".join(lines).strip()
    return result


def _single_line(value):
    """Keep user-provided frontmatter values inside one local text line."""
    return " ".join(str(value).replace("\x00", "").split())


def _normalized_card(data, forecast_id=None, created_at=None):
    """Validate and normalize the public forecast-card fields."""
    title = _single_line(data.get("title", ""))
    criteria = _single_line(data.get("resolution_criteria", ""))
    if not title:
        raise ValueError("预测标题不能为空")
    if not criteria:
        raise ValueError("结算标准不能为空")
    try:
        probability = round(float(data.get("probability")), 2)
    except (TypeError, ValueError):
        raise ValueError("概率必须选择固定档位") from None
    if probability not in ALLOWED_PROBABILITIES:
        raise ValueError("概率必须选择固定档位")
    window_start = _single_line(data.get("window_start", ""))
    window_end = _single_line(data.get("window_end", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", window_start) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", window_end
    ):
        raise ValueError("日期必须使用年月日")
    if window_start > window_end:
        raise ValueError("日期范围不能前后倒置")
    identity = _single_line(forecast_id or data.get("forecast_id", ""))
    if not identity:
        identity = f"F-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", identity):
        raise ValueError("预测编号格式无效")
    return {
        "forecast_id": identity,
        "created_at": _single_line(
            created_at or data.get("created_at") or datetime.now(timezone.utc).isoformat()
        ),
        "status": "open",
        "title": title,
        "resolution_criteria": criteria,
        "window_start": window_start,
        "window_end": window_end,
        "probability": probability,
        "confidence": _single_line(data.get("confidence", "medium")) or "medium",
        "alert_level": _single_line(data.get("alert_level", "L2")) or "L2",
        "next_review_at": _single_line(data.get("next_review_at", window_start)),
        "model_version": _single_line(data.get("model_version", "v0.2")) or "v0.2",
        "privacy_level": _single_line(data.get("privacy_level", "P2")) or "P2",
        "causal_chain": str(data.get("causal_chain", "尚未补充。" )).strip(),
        "supporting_evidence": str(data.get("supporting_evidence", "尚未补充。" )).strip(),
        "opposing_evidence": str(data.get("opposing_evidence", "尚未补充。" )).strip(),
        "alternatives": str(data.get("alternatives", "尚未补充。" )).strip(),
        "falsification": str(data.get("falsification", criteria)).strip(),
        "recommended_action": str(data.get("recommended_action", "继续观察并在复核日更新。" )).strip(),
    }


def _render_card(card):
    """Render the canonical local forecast card used for immutable hashing."""
    return f"""---
forecast_id: {card['forecast_id']}
created_at: {card['created_at']}
status: open
title: {card['title']}
resolution_criteria: {card['resolution_criteria']}
window_start: {card['window_start']}
window_end: {card['window_end']}
probability: {card['probability']:.2f}
confidence: {card['confidence']}
alert_level: {card['alert_level']}
next_review_at: {card['next_review_at']}
model_version: {card['model_version']}
privacy_level: {card['privacy_level']}
---
## 因果链
{card['causal_chain']}
## 支持证据
{card['supporting_evidence']}
## 反对证据
{card['opposing_evidence']}
## 替代假设
{card['alternatives']}
## 反证条件
{card['falsification']}
## 建议行动
{card['recommended_action']}
"""


class ForecastService:
    """Read immutable forecast versions and record explicit resolutions."""

    def __init__(self, database):
        self.database = database

    def list_forecasts(self):
        """Return one summary per forecast using its latest version."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT f.forecast_id, f.status, f.window_end,
                       v.version, v.probability, v.content
                FROM forecasts f
                JOIN forecast_versions v ON v.forecast_id = f.forecast_id
                JOIN (
                    SELECT forecast_id, MAX(version) AS latest_version
                    FROM forecast_versions GROUP BY forecast_id
                ) latest ON latest.forecast_id = v.forecast_id
                         AND latest.latest_version = v.version
                ORDER BY f.window_end, f.forecast_id
                """
            ).fetchall()
        result = []
        for row in rows:
            fields = parse_frontmatter(row["content"])
            result.append(
                {
                    "forecast_id": row["forecast_id"],
                    "status": row["status"],
                    "window_end": row["window_end"],
                    "version": row["version"],
                    "probability": row["probability"],
                    "title": fields.get("title", row["forecast_id"]),
                    "confidence": fields.get("confidence", "unknown"),
                    "alert_level": fields.get("alert_level", "L1"),
                    "resolution_criteria": fields.get("resolution_criteria", ""),
                }
            )
        return result

    def get_forecast(self, forecast_id):
        """Return a forecast summary plus all immutable versions."""
        items = [item for item in self.list_forecasts() if item["forecast_id"] == forecast_id]
        if not items:
            raise KeyError(forecast_id)
        with self.database.connect() as connection:
            versions = [
                dict(row)
                for row in connection.execute(
                    "SELECT version, probability, content FROM forecast_versions WHERE forecast_id = ? ORDER BY version",
                    (forecast_id,),
                ).fetchall()
            ]
        latest_fields = parse_frontmatter(versions[-1]["content"])
        draft = {
            key: latest_fields.get(key, "")
            for key in (
                "title",
                "resolution_criteria",
                "window_start",
                "window_end",
                "probability",
                "confidence",
                "alert_level",
                "privacy_level",
            )
        }
        draft.update(parse_sections(versions[-1]["content"]))
        return {**items[0], "versions": versions, "draft": draft}

    def create_forecast(self, card_data):
        """Create a validated forecast and its first immutable version."""
        card = _normalized_card(card_data)
        content = _render_card(card)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM forecasts WHERE forecast_id = ?", (card["forecast_id"],)
            ).fetchone()
            if exists:
                raise ForecastConflictError("预测编号已经存在")
            connection.execute(
                "INSERT INTO forecasts(forecast_id, status, window_end) VALUES (?, 'open', ?)",
                (card["forecast_id"], card["window_end"]),
            )
            connection.execute(
                "INSERT INTO forecast_versions(forecast_id, version, probability, content_sha256, content) VALUES (?, 1, ?, ?, ?)",
                (card["forecast_id"], card["probability"], digest, content),
            )
            connection.execute(
                "INSERT INTO audit_log(occurred_at, action, object_type, object_id, details_json) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    "forecast.create",
                    "forecast",
                    card["forecast_id"],
                    json.dumps({"version": 1}, ensure_ascii=False),
                ),
            )
        return {"forecast_id": card["forecast_id"], "version": 1, "duplicate": False}

    def add_version(self, forecast_id, card_data):
        """Append a changed immutable version or return the matching latest version."""
        with self.database.connect() as connection:
            latest = connection.execute(
                "SELECT version, content, content_sha256 FROM forecast_versions WHERE forecast_id = ? ORDER BY version DESC LIMIT 1",
                (forecast_id,),
            ).fetchone()
            if latest is None:
                raise KeyError(forecast_id)
            original = parse_frontmatter(latest["content"])
            merged = {**original, **parse_sections(latest["content"]), **card_data}
            card = _normalized_card(
                merged,
                forecast_id=forecast_id,
                created_at=original.get("created_at"),
            )
            content = _render_card(card)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest == latest["content_sha256"]:
                return {
                    "forecast_id": forecast_id,
                    "version": latest["version"],
                    "duplicate": True,
                }
            version = latest["version"] + 1
            connection.execute(
                "INSERT INTO forecast_versions(forecast_id, version, probability, content_sha256, content) VALUES (?, ?, ?, ?, ?)",
                (forecast_id, version, card["probability"], digest, content),
            )
            connection.execute(
                "UPDATE forecasts SET window_end = ? WHERE forecast_id = ?",
                (card["window_end"], forecast_id),
            )
            connection.execute(
                "INSERT INTO audit_log(occurred_at, action, object_type, object_id, details_json) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    "forecast.version.add",
                    "forecast",
                    forecast_id,
                    json.dumps({"version": version}, ensure_ascii=False),
                ),
            )
        return {"forecast_id": forecast_id, "version": version, "duplicate": False}

    def resolve(self, forecast_id, outcome, resolved_at, note):
        """Resolve a forecast once and score binary outcomes."""
        outcomes = {"occurred": 1.0, "not_occurred": 0.0}
        allowed = {*outcomes, "partial", "indeterminate"}
        if outcome not in allowed:
            raise ValueError("不支持的结算结果")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT probability FROM forecast_versions WHERE forecast_id = ? ORDER BY version DESC LIMIT 1",
                (forecast_id,),
            ).fetchone()
            if row is None:
                raise KeyError(forecast_id)
            probability = row[0]
            brier = None if outcome not in outcomes else round((probability - outcomes[outcome]) ** 2, 10)
            connection.execute(
                "INSERT INTO resolutions(forecast_id, outcome, resolved_at, probability, brier_score) VALUES (?, ?, ?, ?, ?)",
                (forecast_id, outcome, resolved_at, probability, brier),
            )
            connection.execute(
                "UPDATE forecasts SET status = 'resolved' WHERE forecast_id = ?",
                (forecast_id,),
            )
            connection.execute(
                "INSERT INTO audit_log(occurred_at, action, object_type, object_id, details_json) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    "forecast.resolve",
                    "forecast",
                    forecast_id,
                    json.dumps({"outcome": outcome, "note": note}, ensure_ascii=False),
                ),
            )
        return {"forecast_id": forecast_id, "outcome": outcome, "brier_score": brier}

    def score_summary(self):
        """Return aggregate binary calibration statistics."""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*), AVG(brier_score) FROM resolutions WHERE brier_score IS NOT NULL"
            ).fetchone()
        return {
            "resolved_binary": row[0],
            "brier_score": None if row[1] is None else round(row[1], 10),
        }
