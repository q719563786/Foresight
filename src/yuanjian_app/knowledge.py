"""Read-only Obsidian discovery and local knowledge indexing."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path


MAX_MARKDOWN_BYTES = 2 * 1024 * 1024


class KnowledgeService:
    """Index selected local vault metadata without writing to source files."""

    def __init__(self, database, home=None):
        self.database = database
        self.home = Path(home or Path.home()).resolve()

    def discover_vaults(self):
        candidates = []
        for base in (self.home / "Obsidian", self.home / "Documents"):
            if not base.is_dir():
                continue
            for path in sorted(base.iterdir()):
                if path.is_dir() and not path.is_symlink() and (path / ".obsidian").is_dir():
                    candidates.append(path.resolve())
                if path.is_dir() and not path.is_symlink():
                    for child in sorted(path.iterdir()):
                        if child.is_dir() and not child.is_symlink() and (child / ".obsidian").is_dir():
                            candidates.append(child.resolve())
        unique = []
        seen = set()
        for path in candidates:
            key = str(path).casefold()
            if key not in seen:
                unique.append({"name": path.name, "path": str(path)})
                seen.add(key)
        return unique

    def index_vault(self, vault_path):
        root = Path(vault_path).resolve()
        try:
            root.relative_to(self.home)
        except ValueError:
            raise ValueError("知识库必须位于当前用户目录内") from None
        detected = {str(Path(item["path"]).resolve()).casefold() for item in self.discover_vaults()}
        if str(root).casefold() not in detected:
            raise ValueError("只能索引已发现的Obsidian知识库")
        vault_id = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:20]
        indexed_at = datetime.now(timezone.utc).isoformat()
        documents = []
        for path in sorted(root.rglob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                resolved = path.resolve()
                relative = resolved.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if path.stat().st_size > MAX_MARKDOWN_BYTES:
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            title = self._title(text, path.stem)
            excerpt = " ".join(text.replace("\x00", "").split())[:400]
            document_id = hashlib.sha256(f"{vault_id}:{relative}".encode("utf-8")).hexdigest()[:24]
            documents.append(
                {
                    "document_id": document_id,
                    "vault_id": vault_id,
                    "relative_path": relative,
                    "title": title,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "indexed_at": indexed_at,
                    "excerpt": excerpt,
                }
            )
        with self.database.connect() as connection:
            for item in documents:
                connection.execute(
                    """
                    INSERT INTO knowledge_documents(document_id, vault_id, relative_path, title, sha256, modified_at, indexed_at, excerpt)
                    VALUES (:document_id, :vault_id, :relative_path, :title, :sha256, :modified_at, :indexed_at, :excerpt)
                    ON CONFLICT(vault_id, relative_path) DO UPDATE SET
                        document_id=excluded.document_id, title=excluded.title,
                        sha256=excluded.sha256, modified_at=excluded.modified_at,
                        indexed_at=excluded.indexed_at, excerpt=excluded.excerpt
                    """,
                    item,
                )
            relative_paths = [item["relative_path"] for item in documents]
            if relative_paths:
                placeholders = ",".join("?" for _ in relative_paths)
                connection.execute(
                    f"DELETE FROM knowledge_documents WHERE vault_id = ? AND relative_path NOT IN ({placeholders})",
                    (vault_id, *relative_paths),
                )
            else:
                connection.execute("DELETE FROM knowledge_documents WHERE vault_id = ?", (vault_id,))
        return {"vault_id": vault_id, "indexed": len(documents), "indexed_at": indexed_at}

    def list_documents(self, query=""):
        query = " ".join(str(query).split())
        sql = "SELECT document_id, vault_id, relative_path, title, sha256, modified_at, indexed_at, excerpt FROM knowledge_documents"
        params = ()
        if query:
            sql += " WHERE title LIKE ? OR excerpt LIKE ? OR relative_path LIKE ?"
            pattern = f"%{query}%"
            params = (pattern, pattern, pattern)
        sql += " ORDER BY title, relative_path"
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    @staticmethod
    def _title(text, fallback):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped.removeprefix("# ").strip()
                if title:
                    return title[:200]
        return fallback[:200]
