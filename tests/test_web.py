import io
import tempfile
import unittest
from pathlib import Path

from loverlist import create_app, services
from loverlist.db import get_connection

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class WebTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "web_test.db"
        self.avatar_dir = Path(tmp.name) / "avatars"
        self.app = create_app(self.db_path, avatar_dir=self.avatar_dir)
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
            data={"code_alpha": "lov", "code_num": "1", "title": "初夏", "tags": "恋爱, 青春"},
            follow_redirects=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("LOV-001".encode("utf-8"), r.data)
        r = self.client.get("/works", query_string={"q": "初夏"})
        self.assertIn("LOV-001".encode("utf-8"), r.data)

    def test_code_parts_required(self):
        r = self.client.post("/works", data={"code_alpha": "", "code_num": ""}, follow_redirects=True)
        self.assertIn("英文部分必填".encode("utf-8"), r.data)
        r = self.client.post("/works", data={"code_alpha": "LOV", "code_num": "abc"}, follow_redirects=True)
        self.assertIn("数字部分必填".encode("utf-8"), r.data)

    def test_work_edit_prefills_split_code(self):
        self.client.post("/works", data={"code_alpha": "lov", "code_num": "7"})
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        r = self.client.get(f"/works/{wid}/edit")
        html = r.data.decode("utf-8")
        self.assertIn('name="code_alpha" required placeholder="LOV" value="LOV"', html)
        self.assertIn('name="code_num" required placeholder="007" value="007"', html)

    def test_duplicate_code_rejected(self):
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001"})
        r = self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001"}, follow_redirects=True)
        self.assertIn("已存在".encode("utf-8"), r.data)

    def test_credit_add_via_web(self):
        self.client.post("/persons", data={"name": "ひなた"})
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001"})
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

    def test_avatar_upload_reject_delete_and_cleanup(self):
        self.client.post("/persons", data={"name": "ひなた"})
        pid = self._first_person_id()
        # 上传合法 PNG → 落盘 + 详情页引用
        r = self.client.post(
            f"/persons/{pid}/avatar",
            data={"file": (io.BytesIO(PNG_1PX), "a.png")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("头像已更新".encode("utf-8"), r.data)
        files = list(self.avatar_dir.glob(f"{pid}_*"))
        self.assertEqual(len(files), 1)
        r = self.client.get(f"/persons/{pid}")
        self.assertIn(f"/avatars/{files[0].name}".encode("utf-8"), r.data)
        self.assertEqual(
            self.client.get(f"/avatars/{files[0].name}").status_code, 200
        )
        # 非图片内容被拒
        r = self.client.post(
            f"/persons/{pid}/avatar",
            data={"file": (io.BytesIO(b"not an image"), "a.txt")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("不支持的图片格式".encode("utf-8"), r.data)
        # 移除 → 文件清空
        r = self.client.post(f"/persons/{pid}/avatar/delete", follow_redirects=True)
        self.assertIn("头像已移除".encode("utf-8"), r.data)
        self.assertEqual(list(self.avatar_dir.glob(f"{pid}_*")), [])
        # 删除人物联动清理头像文件
        self.client.post("/persons", data={"name": "两人"})
        conn = get_connection(self.db_path)
        try:
            pid2 = conn.execute(
                "SELECT id FROM persons WHERE name = '两人'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.client.post(
            f"/persons/{pid2}/avatar",
            data={"file": (io.BytesIO(PNG_1PX), "b.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(len(list(self.avatar_dir.glob(f"{pid2}_*"))), 1)
        self.client.post(f"/persons/{pid2}/delete")
        self.assertEqual(list(self.avatar_dir.glob(f"{pid2}_*")), [])

    def test_favorites_page(self):
        r = self.client.get("/favorites")
        self.assertEqual(r.status_code, 200)
        self.assertIn("心动榜".encode("utf-8"), r.data)


if __name__ == "__main__":
    unittest.main()