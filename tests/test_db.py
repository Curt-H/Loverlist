import sqlite3
import tempfile
import unittest
from pathlib import Path

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

    def test_avatar_column_migration_for_legacy_db(self):
        """无 avatar 列的旧库在 init_db 后自动补列,且数据保留。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "legacy.db"
        old = sqlite3.connect(str(p))
        old.execute(
            "CREATE TABLE persons ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
            " alias TEXT NOT NULL DEFAULT '', kana TEXT NOT NULL DEFAULT '',"
            " gender TEXT NOT NULL DEFAULT '女', birth_ym TEXT NOT NULL DEFAULT '',"
            " height INTEGER, bust INTEGER, waist INTEGER, hip INTEGER,"
            " cup TEXT NOT NULL DEFAULT '', heart_count INTEGER NOT NULL DEFAULT 0,"
            " is_favorite INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',"
            " created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))"
        )
        old.execute("INSERT INTO persons (name) VALUES ('旧数据')")
        old.commit()
        old.close()

        conn = db.get_connection(p)
        try:
            db.init_db(conn)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(persons)")}
            self.assertIn("avatar", cols)
            row = conn.execute("SELECT name, avatar FROM persons").fetchone()
            self.assertEqual((row["name"], row["avatar"]), ("旧数据", ""))
        finally:
            conn.close()


    def test_is_vr_column_migration_for_legacy_db(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "legacy2.db"
        old = sqlite3.connect(str(p))
        old.execute(
            "CREATE TABLE works (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,"
            " title TEXT NOT NULL DEFAULT '', filename TEXT NOT NULL DEFAULT '',"
            " status TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',"
            " created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))"
        )
        old.execute("INSERT INTO works (code) VALUES ('LOV-001')")
        old.commit()
        old.close()
        conn = db.get_connection(p)
        try:
            db.init_db(conn)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(works)")}
            self.assertIn("is_vr", cols)
            row = conn.execute("SELECT code, status, is_vr FROM works").fetchone()
            self.assertEqual((row["code"], row["status"], row["is_vr"]),
                             ("LOV-001", "已收录", 0))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()