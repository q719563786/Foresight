import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .external_sources import (
    FetchError,
    fetch_bytes,
    parse_feed,
    parse_gdelt,
    parse_html_list,
    validate_public_url,
)
from .text_cleaning import plain_text


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def canonicalize_url(url):
    parts = urlsplit(validate_public_url(url))
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"spm", "from", "source"}
    ]
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))


def fetch_source(source):
    body = fetch_bytes(source["endpoint"])
    kind = source["kind"]
    if kind == "rss":
        return parse_feed(body, source["source_id"], source["name"], source["endpoint"])
    if kind == "gdelt":
        return parse_gdelt(body, source["source_id"], source["name"])
    if kind == "html_list":
        return parse_html_list(body, source["source_id"], source["name"], source["endpoint"])
    raise FetchError("unsupported", f"不支持的数据源类型：{kind}")


class ExternalRadarService:
    def __init__(
        self, database, fetcher=fetch_source, now=utc_now, on_item_stored=None
    ):
        self.database = database
        self.fetcher = fetcher
        self.now = now
        self.on_item_stored = on_item_stored

    def ensure_public_defaults(self):
        defaults = (
            {
                "source_id": "S-BBC-ZH",
                "name": "BBC中文RSS",
                "kind": "rss",
                "endpoint": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
                "reliability_weight": 0.75,
            },
            {
                "source_id": "S-MOHRSS-POLICY",
                "name": "人力资源社会保障部政策解读",
                "kind": "rss",
                "endpoint": "http://www.mohrss.gov.cn/gkml/zcjd/rss.xml",
                "reliability_weight": 0.95,
                "config": {"primary_source": True},
            },
            {
                "source_id": "S-MFA-SAFETY",
                "name": "外交部领事安全提醒",
                "kind": "html_list",
                "endpoint": "https://cs.mfa.gov.cn/rss/",
                "reliability_weight": 0.95,
                "config": {"primary_source": True},
            },
            {
                "source_id": "S-GDELT-CHINA",
                "name": "GDELT全球新闻索引",
                "kind": "gdelt",
                "endpoint": "https://api.gdeltproject.org/api/v2/doc/doc?query=China&mode=artlist&format=json&maxrecords=25&timespan=1d",
                "reliability_weight": 0.65,
            },
        )
        with self.database.connect() as connection:
            existing = {
                row[0]
                for row in connection.execute("SELECT source_id FROM external_sources")
            }
        for source in defaults:
            if source["source_id"] not in existing:
                self.add_source(source)

    def add_source(self, data):
        source_id = str(data.get("source_id") or f"S-{uuid.uuid4().hex[:12]}")
        name = str(data.get("name", "")).strip()
        kind = str(data.get("kind", "rss")).strip()
        endpoint = validate_public_url(data.get("endpoint", ""))
        refresh = int(data.get("refresh_minutes", 15))
        reliability = float(data.get("reliability_weight", 0.6))
        if not name or kind not in {"rss", "gdelt", "html_list"}:
            raise ValueError("数据源名称或类型无效")
        if refresh < 5 or refresh > 1440 or not 0 <= reliability <= 1:
            raise ValueError("刷新周期或可靠度无效")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO external_sources(
                    source_id, name, kind, endpoint, enabled, refresh_minutes,
                    reliability_weight, config_json, next_fetch_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    name,
                    kind,
                    endpoint,
                    1 if data.get("enabled", True) else 0,
                    refresh,
                    reliability,
                    json.dumps(data.get("config", {}), ensure_ascii=False),
                    iso(self.now()),
                ),
            )
        return source_id

    def add_watch_rule(self, data):
        query = " ".join(str(data.get("query", "")).split())
        importance = int(data.get("importance", 3))
        if not query or not 1 <= importance <= 5:
            raise ValueError("关注词或重要度无效")
        with self.database.connect() as connection:
            existing = next(
                (
                    row
                    for row in connection.execute(
                        "SELECT rule_id, query, importance FROM watch_rules"
                    )
                    if row["query"].casefold() == query.casefold()
                ),
                None,
            )
            if existing is not None:
                if importance > existing["importance"]:
                    connection.execute(
                        "UPDATE watch_rules SET importance = ? WHERE rule_id = ?",
                        (importance, existing["rule_id"]),
                    )
                return existing["rule_id"]
            rule_id = str(data.get("rule_id") or f"W-{uuid.uuid4().hex[:12]}")
            connection.execute(
                """
                INSERT INTO watch_rules(
                    rule_id, query, domains_json, interest_ids_json,
                    importance, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    query,
                    json.dumps(data.get("domains", []), ensure_ascii=False),
                    json.dumps(data.get("interest_ids", []), ensure_ascii=False),
                    importance,
                    1 if data.get("enabled", True) else 0,
                    iso(self.now()),
                ),
            )
        return rule_id

    def list_rules(self):
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM watch_rules ORDER BY importance DESC, created_at"
            ).fetchall()
        return [
            {
                **dict(row),
                "domains": json.loads(row["domains_json"]),
                "interest_ids": json.loads(row["interest_ids_json"]),
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]

    def list_sources(self):
        now = self.now()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM external_sources ORDER BY name"
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            last_success = parse_iso(row["last_success_at"])
            item["enabled"] = bool(row["enabled"])
            item["stale"] = bool(
                last_success
                and now - last_success > timedelta(minutes=row["refresh_minutes"] * 2)
            )
            output.append(item)
        return output

    def set_source_enabled(self, source_id, enabled):
        with self.database.connect() as connection:
            result = connection.execute(
                """
                UPDATE external_sources SET enabled = ?, next_fetch_at = CASE
                    WHEN ? = 1 THEN ? ELSE next_fetch_at END
                WHERE source_id = ?
                """,
                (1 if enabled else 0, 1 if enabled else 0, iso(self.now()), source_id),
            )
            if result.rowcount != 1:
                raise KeyError(source_id)
        return {"source_id": source_id, "enabled": bool(enabled)}

    def _source(self, source_id):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM external_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
        if row is None:
            raise KeyError(source_id)
        return dict(row)

    def _match(self, connection, item_id, title, summary, reliability):
        text = f"{title}\n{summary}".casefold()
        rules = connection.execute(
            "SELECT * FROM watch_rules WHERE enabled = 1"
        ).fetchall()
        for rule in rules:
            query = rule["query"].casefold()
            if query not in text:
                continue
            title_hit = query in title.casefold()
            score = min(1.0, 0.15 * rule["importance"] + 0.2 * reliability + (0.15 if title_hit else 0.05))
            alert = "L4" if score >= 0.9 else "L3" if score >= 0.7 else "L2" if score >= 0.5 else "L1"
            reasons = [f"命中关注词：{rule['query']}", f"关注重要度：{rule['importance']}/5"]
            connection.execute(
                """
                INSERT INTO external_matches(item_id, rule_id, score, reasons_json, alert_level)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(item_id, rule_id) DO UPDATE SET
                    score=excluded.score,
                    reasons_json=excluded.reasons_json,
                    alert_level=excluded.alert_level
                """,
                (item_id, rule["rule_id"], score, json.dumps(reasons, ensure_ascii=False), alert),
            )

    def _store_item(self, connection, source, item, fetched_at):
        canonical = canonicalize_url(item.url)
        item_id = "E-" + hashlib.sha256(canonical.encode()).hexdigest()[:24]
        title = plain_text(item.title, max_length=300)
        summary = plain_text(item.summary, max_length=2000)
        content_hash = hashlib.sha256(
            f"{title}\n{summary}".encode("utf-8")
        ).hexdigest()
        exists = connection.execute(
            "SELECT item_id FROM external_items WHERE canonical_url = ?", (canonical,)
        ).fetchone()
        new = exists is None
        if exists is not None:
            item_id = exists["item_id"]
            connection.execute(
                "UPDATE external_items SET last_seen_at = ?, fetched_at = ? WHERE item_id = ?",
                (fetched_at, fetched_at, item_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO external_items(
                    item_id, canonical_url, title, summary, published_at, fetched_at,
                    source_id, source_name, language, content_hash, first_seen_at,
                    last_seen_at, source_count, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    item_id,
                    canonical,
                    title,
                    summary,
                    item.published_at or None,
                    fetched_at,
                    source["source_id"],
                    source["name"],
                    item.language,
                    content_hash,
                    fetched_at,
                    fetched_at,
                    json.dumps(item.raw or {}, ensure_ascii=False),
                ),
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO external_item_sources(item_id, source_id, url, first_seen_at)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, source["source_id"], item.url, fetched_at),
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM external_item_sources WHERE item_id = ?", (item_id,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE external_items SET source_count = ? WHERE item_id = ?", (count, item_id)
        )
        self._match(
            connection,
            item_id,
            title,
            summary,
            source["reliability_weight"],
        )
        return new, item_id

    def _notify_stored_items(self, item_ids):
        if self.on_item_stored is None:
            return
        for item_id in dict.fromkeys(item_ids):
            try:
                self.on_item_stored(item_id)
            except Exception as error:
                with self.database.connect() as connection:
                    connection.execute(
                        """
                        INSERT INTO audit_log(
                            occurred_at,action,object_type,object_id,details_json
                        ) VALUES (?, 'cognition.process_failed', 'external_item', ?, ?)
                        """,
                        (
                            iso(self.now()),
                            item_id,
                            json.dumps(
                                {
                                    "error_type": type(error).__name__,
                                    "message": str(error),
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )

    def refresh_source(self, source_id):
        source = self._source(source_id)
        started = self.now()
        run_id = "R-" + uuid.uuid4().hex
        try:
            items = self.fetcher(source)
            fetched_at = iso(self.now())
            new_count = 0
            stored_item_ids = []
            with self.database.connect() as connection:
                for item in items:
                    is_new, item_id = self._store_item(
                        connection, source, item, fetched_at
                    )
                    new_count += int(is_new)
                    stored_item_ids.append(item_id)
                next_fetch = iso(self.now() + timedelta(minutes=source["refresh_minutes"]))
                connection.execute(
                    """
                    UPDATE external_sources SET last_attempt_at=?, last_success_at=?,
                        last_status='ok', last_error='', consecutive_failures=0,
                        next_fetch_at=? WHERE source_id=?
                    """,
                    (fetched_at, fetched_at, next_fetch, source_id),
                )
                connection.execute(
                    "INSERT INTO external_runs VALUES (?, ?, ?, ?, 'ok', ?, ?, '', '')",
                    (run_id, source_id, iso(started), fetched_at, len(items), new_count),
                )
            self._notify_stored_items(stored_item_ids)
            return {"status": "ok", "fetched_count": len(items), "new_count": new_count}
        except FetchError as error:
            finished = self.now()
            failures = source["consecutive_failures"] + 1
            delay = min(60, 15 * (2 ** (failures - 1)))
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE external_sources SET last_attempt_at=?, last_status='error',
                        last_error=?, consecutive_failures=?, next_fetch_at=? WHERE source_id=?
                    """,
                    (iso(finished), str(error), failures, iso(finished + timedelta(minutes=delay)), source_id),
                )
                connection.execute(
                    "INSERT INTO external_runs VALUES (?, ?, ?, ?, 'error', 0, 0, ?, ?)",
                    (run_id, source_id, iso(started), iso(finished), error.error_type, str(error)),
                )
            return {"status": "error", "error_type": error.error_type, "message": str(error)}

    def radar_items(self, limit=100):
        with self.database.connect() as connection:
            items = connection.execute(
                """
                SELECT e.*, MAX(m.score) AS best_score
                FROM external_items e
                JOIN external_matches m ON m.item_id = e.item_id
                GROUP BY e.item_id
                ORDER BY best_score DESC, COALESCE(e.published_at, e.first_seen_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            output = []
            for item in items:
                matches = connection.execute(
                    """
                    SELECT m.score, m.reasons_json, m.alert_level, w.rule_id, w.query,
                           w.importance
                    FROM external_matches m JOIN watch_rules w ON w.rule_id=m.rule_id
                    WHERE m.item_id=? ORDER BY m.score DESC
                    """,
                    (item["item_id"],),
                ).fetchall()
                best_alert = max(
                    (match["alert_level"] for match in matches),
                    key=lambda value: int(value[1:]),
                )
                row = dict(item)
                row["title"] = plain_text(row.get("title"), max_length=300)
                row["summary"] = plain_text(row.get("summary"), max_length=2000)
                row["alert_level"] = best_alert
                row["matched_rules"] = [
                    {
                        "rule_id": match["rule_id"],
                        "query": match["query"],
                        "importance": match["importance"],
                        "score": match["score"],
                        "reasons": json.loads(match["reasons_json"]),
                    }
                    for match in matches
                ]
                output.append(row)
        return output

    def refresh_due_sources(self):
        due_at = iso(self.now())
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_id FROM external_sources
                WHERE enabled = 1 AND (next_fetch_at IS NULL OR next_fetch_at <= ?)
                ORDER BY source_id
                """,
                (due_at,),
            ).fetchall()
        for row in rows:
            self.refresh_source(row["source_id"])
        return len(rows)
