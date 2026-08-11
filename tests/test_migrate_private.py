import sqlite3
import tempfile
import unittest
import importlib.util
from pathlib import Path

module_path = Path(__file__).parents[1] / "tools" / "migrate_private_v05.py"
spec = importlib.util.spec_from_file_location("migrate_private_v05", module_path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
counts = migration.counts
integrity = migration.integrity


class PrivateMigrationToolTests(unittest.TestCase):
    def test_read_helpers_release_windows_database_handle(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "source.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE forecasts(forecast_id TEXT)")
            connection.commit()
            connection.close()

            self.assertEqual(integrity(database), "ok")
            self.assertEqual(counts(database)["forecasts"], 0)
            moved = database.with_name("moved.db")
            database.replace(moved)

            self.assertTrue(moved.is_file())


if __name__ == "__main__":
    unittest.main()
