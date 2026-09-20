import tempfile
import unittest
from pathlib import Path

from loverlist import create_app, services
from loverlist.db import get_connection


class WebTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "web_test.db"
        self.app = create_app(self.db_path)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _first_person_id(self):
        conn = get_connection(self.db_path)
        try:
            return conn.execute("SELECT id FROM persons LIMIT 1").fetchone()[0]
        finally:
            conn.close()

    def test_dashboard_ok(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Loverlist".encode("utf-8"), r.data)

    def test_person_create_flow(self):
        r = self.client.post(
            "/persons",
            data={"name": "鈴木愛理", "gender": "女", "height": "160"},
            follow_redirects=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("鈴木愛理".encode("utf-8"), r.data)
        r = self.client.get("/persons")
        self.assertIn("鈴木愛理".encode("utf-8"), r.data)

    def test_empty_name_rejected(self):
        r = self.client.post("/persons", data={"name": ""}, follow_redirects=True)
        self.assertIn("姓名必填".encode("utf-8"), r.data)

    def test_heart_ajax(self):
        self.client.post("/persons", data={"name": "ひなた"})
        pid = self._first_person_id()
        r = self.client.post(f"/persons/{pid}/heart")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["heart_count"], 1)
        r = self.client.post(f"/persons/{pid}/favorite")
        self.assertEqual(r.get_json()["is_favorite"], 1)

    def test_work_create_and_detail(self):
        r = self.client.post(
            "/works",
            data={"code": "lov-001", "title": "初夏", "tags": "恋爱, 青春"},
            follow_redirects=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("LOV-001".encode("utf-8"), r.data)
        r = self.client.get("/works", query_string={"q": "初夏"})
        self.assertIn("LOV-001".encode("utf-8"), r.data)

    def test_duplicate_code_rejected(self):
        self.client.post("/works", data={"code": "LOV-001"})
        r = self.client.post("/works", data={"code": "LOV-001"}, follow_redirects=True)
        self.assertIn("已存在".encode("utf-8"), r.data)

    def test_credit_add_via_web(self):
        self.client.post("/persons", data={"name": "ひなた"})
        self.client.post("/works", data={"code": "LOV-001"})
        pid = self._first_person_id()
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        r = self.client.post(
            f"/works/{wid}/credits",
            data={"person_id": str(pid), "role": "", "character_name": "小夏"},
            follow_redirects=True,
        )
        self.assertIn("ひなた".encode("utf-8"), r.data)

    def test_favorites_page(self):
        r = self.client.get("/favorites")
        self.assertEqual(r.status_code, 200)
        self.assertIn("心动榜".encode("utf-8"), r.data)


if __name__ == "__main__":
    unittest.main()