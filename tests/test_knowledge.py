import hashlib
import tempfile
import unittest
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.knowledge import KnowledgeService


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)
        self.vault = self.home / "Obsidian" / "TestVault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.article = self.vault / "articles" / "view.md"
        self.article.parent.mkdir()
        self.article.write_text("# 登高测试\n\n只读知识正文。", encoding="utf-8")
        self.database = Database(self.home / "private" / "yuanjian.db")
        self.database.initialize()
        self.service = KnowledgeService(self.database, home=self.home)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discovers_vault_and_indexes_markdown_without_modifying_source(self):
        before = digest(self.article)

        vaults = self.service.discover_vaults()
        result = self.service.index_vault(vaults[0]["path"])
        documents = self.service.list_documents()

        self.assertEqual(len(vaults), 1)
        self.assertEqual(result["indexed"], 1)
        self.assertEqual(digest(self.article), before)
        self.assertEqual(documents[0]["relative_path"], "articles/view.md")
        self.assertEqual(documents[0]["title"], "登高测试")
        self.assertNotIn(str(self.home), str(documents[0]))

    def test_index_skips_oversized_markdown_and_supports_search(self):
        (self.vault / "large.md").write_text("x" * (2 * 1024 * 1024 + 1), encoding="utf-8")
        self.service.index_vault(self.vault)

        matches = self.service.list_documents("登高")
        misses = self.service.list_documents("不存在")

        self.assertEqual(len(matches), 1)
        self.assertEqual(misses, [])


if __name__ == "__main__":
    unittest.main()
