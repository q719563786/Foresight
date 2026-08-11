"""Local event clusters and evidence grading for the external radar."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from .clustering import ClusterText, should_merge
from .external_sources import normalize_published_at


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "unknown").casefold()


def _json_object(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _categories(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".casefold()
    rules = (
        ("health", ("医保", "医疗", "医院", "药品", "手术", "健康")),
        ("finance", ("银行", "利率", "贷款", "信用", "黄金", "比特币", "保险")),
        ("employment", ("就业", "工资", "社保", "公积金", "招聘")),
        ("safety", ("安全", "事故", "灾害", "台风", "暴雨", "火灾")),
        ("policy", ("政策", "新规", "条例", "通知", "办法")),
        ("technology", ("人工智能", "ai", "软件", "网络", "数据")),
    )
    found = [category for category, words in rules if any(word in text for word in words)]
    return found or ["general"]


class CognitionService:
    def __init__(self, database, now=lambda: datetime.now(timezone.utc)):
        self.database = database
        self.now = now

    def _load_item(self, connection, item_id):
        row = connection.execute(
            "SELECT * FROM external_items WHERE item_id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row

    def _source_facts(self, connection, cluster_id):
        rows = connection.execute(
            """
            SELECT ci.item_id, eis.source_id, eis.url, s.config_json,
                   e.canonical_url, e.source_id AS original_source_id
            FROM event_cluster_items ci
            JOIN external_items e ON e.item_id=ci.item_id
            LEFT JOIN external_item_sources eis ON eis.item_id=ci.item_id
            LEFT JOIN external_sources s ON s.source_id=eis.source_id
            WHERE ci.cluster_id=?
            ORDER BY ci.item_id, eis.source_id
            """,
            (cluster_id,),
        ).fetchall()
        facts = []
        for row in rows:
            source_id = row["source_id"] or row["original_source_id"]
            url = row["url"] or row["canonical_url"]
            config = _json_object(row["config_json"])
            facts.append(
                {
                    "item_id": row["item_id"],
                    "source_id": source_id,
                    "domain": _domain(url),
                    "primary": bool(config.get("primary_source", False)),
                }
            )
        return facts

    def _recalculate(self, connection, cluster_id, previous_hash):
        item_rows = connection.execute(
            """
            SELECT e.item_id, e.content_hash, e.published_at, e.first_seen_at
            FROM event_cluster_items ci
            JOIN external_items e ON e.item_id=ci.item_id
            WHERE ci.cluster_id=? ORDER BY e.item_id
            """,
            (cluster_id,),
        ).fetchall()
        facts = self._source_facts(connection, cluster_id)
        domains = {fact["domain"] for fact in facts}
        primary_sources = {
            fact["source_id"] for fact in facts if fact["primary"]
        }
        evidence_payload = {
            "items": [
                {
                    "item_id": row["item_id"],
                    "content_hash": row["content_hash"],
                    "observed_at": row["published_at"] or row["first_seen_at"],
                }
                for row in item_rows
            ],
            "sources": facts,
        }
        evidence_hash = hashlib.sha256(
            json.dumps(
                evidence_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if primary_sources and len(domains) >= 3:
            level = "E4"
        elif primary_sources and len(domains) >= 2:
            level = "E3"
        elif len(domains) >= 2:
            level = "E2"
        else:
            level = "E1"
        changed = evidence_hash != previous_hash
        connection.execute(
            """
            UPDATE event_clusters SET evidence_level=?, evidence_hash=?,
                independent_domains=?, primary_source_count=?,
                needs_judgment=CASE WHEN ? THEN 1 ELSE needs_judgment END,
                updated_at=? WHERE cluster_id=?
            """,
            (
                level,
                evidence_hash,
                len(domains),
                len(primary_sources),
                1 if changed else 0,
                _iso(self.now()),
                cluster_id,
            ),
        )
        return level, evidence_hash, changed

    def process_item(self, item_id: str) -> dict:
        with self.database.connect() as connection:
            item = self._load_item(connection, item_id)
            existing = connection.execute(
                "SELECT cluster_id FROM event_cluster_items WHERE item_id=?",
                (item_id,),
            ).fetchone()
            observed_text = normalize_published_at(item["published_at"]) or item[
                "first_seen_at"
            ]
            observed_at = _parse_time(observed_text)
            decision = None
            if existing:
                cluster_id = existing["cluster_id"]
            else:
                best = None
                candidates = connection.execute(
                    "SELECT * FROM event_clusters WHERE status='active' ORDER BY last_seen_at DESC"
                ).fetchall()
                current = ClusterText(item["title"], item["summary"], observed_at)
                for candidate in candidates:
                    comparison = should_merge(
                        current,
                        ClusterText(
                            candidate["title"],
                            candidate["summary"],
                            _parse_time(candidate["last_seen_at"]),
                        ),
                    )
                    if comparison.merge and (best is None or comparison.score > best.score):
                        best = comparison
                        cluster_id = candidate["cluster_id"]
                decision = best
                if decision is None:
                    cluster_id = "C-" + uuid.uuid4().hex
                    timestamp = _iso(self.now())
                    connection.execute(
                        """
                        INSERT INTO event_clusters(
                            cluster_id,title,summary,first_seen_at,last_seen_at,
                            evidence_hash,categories_json,created_at,updated_at
                        ) VALUES (?,?,?,?,?,'',?,?,?)
                        """,
                        (
                            cluster_id,
                            item["title"],
                            item["summary"],
                            _iso(observed_at),
                            _iso(observed_at),
                            json.dumps(_categories(item["title"], item["summary"])),
                            timestamp,
                            timestamp,
                        ),
                    )
                    similarity_score = 1.0
                    merge_reason = "new_cluster"
                    shared_entities = ()
                else:
                    similarity_score = decision.score
                    merge_reason = decision.reason
                    shared_entities = decision.shared_entities
                    connection.execute(
                        """
                        UPDATE event_clusters SET
                            first_seen_at=MIN(first_seen_at, ?),
                            last_seen_at=MAX(last_seen_at, ?), updated_at=?
                        WHERE cluster_id=?
                        """,
                        (_iso(observed_at), _iso(observed_at), _iso(self.now()), cluster_id),
                    )

                source_rows = connection.execute(
                    """
                    SELECT eis.url, s.config_json FROM external_item_sources eis
                    LEFT JOIN external_sources s ON s.source_id=eis.source_id
                    WHERE eis.item_id=? ORDER BY eis.source_id
                    """,
                    (item_id,),
                ).fetchall()
                source_domain = _domain(
                    source_rows[0]["url"] if source_rows else item["canonical_url"]
                )
                is_primary = any(
                    bool(_json_object(row["config_json"]).get("primary_source"))
                    for row in source_rows
                )
                connection.execute(
                    """
                    INSERT INTO event_cluster_items(
                        cluster_id,item_id,similarity,merge_reason,source_domain,
                        is_primary,added_at
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        cluster_id,
                        item_id,
                        similarity_score,
                        merge_reason,
                        source_domain,
                        1 if is_primary else 0,
                        _iso(self.now()),
                    ),
                )
                for entity in shared_entities:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO event_entities(
                            entity_id,cluster_id,name,normalized_name,category,confidence
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            "N-" + uuid.uuid4().hex,
                            cluster_id,
                            entity,
                            entity.casefold(),
                            "shared_term",
                            similarity_score,
                        ),
                    )

            cluster = connection.execute(
                "SELECT evidence_hash FROM event_clusters WHERE cluster_id=?",
                (cluster_id,),
            ).fetchone()
            level, evidence_hash, changed = self._recalculate(
                connection, cluster_id, cluster["evidence_hash"]
            )
            state = connection.execute(
                "SELECT needs_judgment FROM event_clusters WHERE cluster_id=?",
                (cluster_id,),
            ).fetchone()
        return {
            "cluster_id": cluster_id,
            "evidence_level": level,
            "evidence_hash": evidence_hash,
            "changed": changed,
            "needs_judgment": bool(state["needs_judgment"]),
        }

    def backfill_unclustered(self, limit: int = 1000) -> dict:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.item_id FROM external_items e
                LEFT JOIN event_cluster_items ci ON ci.item_id=e.item_id
                WHERE ci.item_id IS NULL
                ORDER BY COALESCE(e.published_at,e.first_seen_at), e.item_id
                LIMIT ?
                """,
                (max(1, min(int(limit), 10000)),),
            ).fetchall()
        for row in rows:
            self.process_item(row["item_id"])
        return {"processed": len(rows), "remaining": self._unclustered_count()}

    def _unclustered_count(self):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT COUNT(*) FROM external_items e
                LEFT JOIN event_cluster_items ci ON ci.item_id=e.item_id
                WHERE ci.item_id IS NULL
                """
            ).fetchone()[0]

    def list_clusters(self, limit: int = 100) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, COUNT(ci.item_id) AS item_count
                FROM event_clusters c
                LEFT JOIN event_cluster_items ci ON ci.cluster_id=c.cluster_id
                GROUP BY c.cluster_id
                ORDER BY c.last_seen_at DESC LIMIT ?
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [self._cluster_dict(row) for row in rows]

    def get_cluster(self, cluster_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM event_clusters WHERE cluster_id=?", (cluster_id,)
            ).fetchone()
            if row is None:
                raise KeyError(cluster_id)
            items = connection.execute(
                """
                SELECT ci.*, e.title, e.summary, e.canonical_url, e.published_at
                FROM event_cluster_items ci
                JOIN external_items e ON e.item_id=ci.item_id
                WHERE ci.cluster_id=? ORDER BY ci.added_at, ci.item_id
                """,
                (cluster_id,),
            ).fetchall()
            entities = connection.execute(
                "SELECT * FROM event_entities WHERE cluster_id=? ORDER BY confidence DESC,name",
                (cluster_id,),
            ).fetchall()
        result = self._cluster_dict(row)
        result["items"] = [dict(item) for item in items]
        result["entities"] = [dict(entity) for entity in entities]
        return result

    @staticmethod
    def _cluster_dict(row):
        result = dict(row)
        result["categories"] = json.loads(result.pop("categories_json"))
        result["needs_judgment"] = bool(result["needs_judgment"])
        return result


class CognitionController:
    """Coordinates clustering, judgments, private impacts and notifications."""

    def __init__(
        self,
        database,
        cognition,
        trends,
        judgment_queue,
        impacts,
        notifications,
        ai_settings,
        now=lambda: datetime.now(timezone.utc),
    ):
        self.database = database
        self.cognition = cognition
        self.trends = trends
        self.judgment_queue = judgment_queue
        self.impacts = impacts
        self.notifications = notifications
        self.ai_settings = ai_settings
        self.now = now

    def _bundle(self, cluster_id):
        from .judgments import build_public_bundle

        cluster = self.cognition.get_cluster(cluster_id)
        return build_public_bundle(cluster, cluster["items"])

    def _provider_name(self):
        remote = self.ai_settings.create_remote_provider()
        if remote is not None:
            self.judgment_queue.providers[remote.name] = remote
            return remote.name
        return "local"

    def process_once(self):
        backfill = self.cognition.backfill_unclustered(limit=1000)
        provider = self._provider_name()
        clusters = [
            item for item in self.cognition.list_clusters(limit=1000) if item["needs_judgment"]
        ]
        for cluster in clusters:
            self.judgment_queue.enqueue(
                cluster["cluster_id"], cluster["evidence_hash"], provider
            )
        judgments = self.judgment_queue.run_due(limit=30)
        mapped = 0
        notified = 0
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT j.judgment_id,j.cluster_id,c.evidence_hash
                FROM judgments j
                JOIN event_clusters c ON c.latest_judgment_id=j.judgment_id
                ORDER BY j.created_at
                """
            ).fetchall()
        for row in rows:
            results = self.impacts.map_judgment(row["cluster_id"], row["judgment_id"])
            mapped += len(results)
            for impact in results:
                candidate = impact.get("candidate", {})
                try:
                    window_days = max(
                        0,
                        (
                            date.fromisoformat(candidate["window_end"])
                            - self.now().date()
                        ).days,
                    )
                except (KeyError, TypeError, ValueError):
                    window_days = 30
                notification = self.notifications.consider(
                    {
                        **impact,
                        "evidence_hash": row["evidence_hash"],
                        "action_window_hours": window_days * 24,
                    },
                    impact["reason"],
                )
                notified += int(notification["status"] == "created")
        return {
            "backfill": backfill,
            "queued": len(clusters),
            "judgments": judgments,
            "mapped_impacts": mapped,
            "notifications_created": notified,
            "provider": provider,
        }

    def capture_trends(self):
        return self.trends.capture(self.now())

    def run_once(self):
        result = self.process_once()
        result["trends"] = self.capture_trends()
        return result

    def status(self):
        with self.database.connect() as connection:
            counts = {
                "clusters": connection.execute(
                    "SELECT COUNT(*) FROM event_clusters"
                ).fetchone()[0],
                "needs_judgment": connection.execute(
                    "SELECT COUNT(*) FROM event_clusters WHERE needs_judgment=1"
                ).fetchone()[0],
                "queued_jobs": connection.execute(
                    "SELECT COUNT(*) FROM judgment_jobs WHERE status IN ('queued','retry','queued_budget')"
                ).fetchone()[0],
                "unread_notifications": connection.execute(
                    "SELECT COUNT(*) FROM notification_log WHERE status='unread'"
                ).fetchone()[0],
            }
            states = {
                row["state_key"]: json.loads(row["value_json"])
                for row in connection.execute(
                    "SELECT state_key,value_json FROM runtime_state WHERE state_key LIKE 'task.%'"
                )
            }
        return {**counts, "tasks": states, "ai": self.ai_settings.get()}

    def list_jobs(self, limit=100):
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id,cluster_id,evidence_hash,provider,model,status,
                       attempts,request_chars,created_at,next_attempt_at,
                       finished_at,last_error
                FROM judgment_jobs ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def cluster_detail(self, cluster_id):
        result = self.cognition.get_cluster(cluster_id)
        judgment_id = result.get("latest_judgment_id")
        result["judgment"] = None
        result["impacts"] = []
        if not judgment_id:
            return result
        with self.database.connect() as connection:
            judgment = connection.execute(
                "SELECT content_json,provider,created_at FROM judgments WHERE judgment_id=?",
                (judgment_id,),
            ).fetchone()
            impacts = connection.execute(
                """
                SELECT p.*,i.name AS interest_name FROM personal_impacts p
                LEFT JOIN interest_objects i ON i.object_id=p.interest_id
                WHERE p.cluster_id=? AND p.judgment_id=?
                ORDER BY p.impact_score DESC
                """,
                (cluster_id, judgment_id),
            ).fetchall()
        if judgment:
            result["judgment"] = {
                **json.loads(judgment["content_json"]),
                "provider": judgment["provider"],
                "created_at": judgment["created_at"],
            }
        for row in impacts:
            item = dict(row)
            item["components"] = json.loads(item.pop("components_json"))
            item["candidate"] = json.loads(item.pop("candidate_json"))
            result["impacts"].append(item)
        return result

    def feedback(self, cluster_id, action, payload=None):
        payload = payload or {}
        now = self.now().astimezone(timezone.utc)
        if action == "mute":
            hours = max(1, min(int(payload.get("hours", 24 * 7)), 24 * 365))
            field, value = "muted_until", _iso(now + timedelta(hours=hours))
        elif action == "lower_importance":
            importance = max(1, min(int(payload.get("importance", 1)), 5))
            field, value = "importance_override", importance
        elif action == "false_positive":
            field, value = "user_label", "false_positive"
        else:
            raise ValueError("反馈动作无效")
        with self.database.connect() as connection:
            result = connection.execute(
                f"UPDATE personal_impacts SET {field}=?,updated_at=? WHERE cluster_id=?",
                (value, _iso(now), cluster_id),
            )
            if result.rowcount == 0:
                raise KeyError(cluster_id)
        return {"cluster_id": cluster_id, "action": action, "updated": result.rowcount}
