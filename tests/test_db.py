import sqlite3
import unittest

from loverlist import db

from tests.helpers import make_conn


class DbTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_creates_all_tables(self):
        names = {
            r[0]
            for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        self.assertLessEqual(
            {"persons", "agency_history", "works", "work_tags", "credits"}, names
        )

    def test_foreign_keys_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO credits (person_id, work_id, role) VALUES (1, 1, '出演')"
            )

    def test_person_defaults(self):
        cur = self.conn.execute("INSERT INTO persons (name) VALUES ('测试')")
        row = self.conn.execute(
            "SELECT * FROM persons WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        self.assertEqual(row["gender"], "女")
        self.assertEqual(row["heart_count"], 0)
        self.assertEqual(row["is_favorite"], 0)

    def test_work_code_unique(self):
        self.conn.execute(
            "INSERT INTO works (code) VALUES ('LOV-001')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO works (code) VALUES ('LOV-001')")


if __name__ == "__main__":
    unittest.main()