import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from loverlist import config, create_app


class ConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        patcher = mock.patch.object(config, "CONFIG_PATH", self.tmp / "data.ini")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_save_roundtrip(self):
        self.assertIsNone(config.load_data_dir())          # 未配置
        config.save_data_dir(r"\\NAS\share\LoverlistData")
        self.assertEqual(config.load_data_dir(), r"\\NAS\share\LoverlistData")
        config.save_data_dir("D:\\Data")
        self.assertEqual(config.load_data_dir(), "D:\\Data")

    def test_check_dir(self):
        self.assertIsNone(config.check_dir(str(self.tmp / "newdir")))   # 自动创建
        blocker = self.tmp / "file.txt"
        blocker.write_text("x", encoding="utf-8")
        self.assertIsNotNone(config.check_dir(str(blocker / "sub")))    # 文件下建目录 → 错误

    def test_copy_local_data(self):
        src = self.tmp / "src"
        (src / "avatars").mkdir(parents=True)
        (src / "loverlist.db").write_bytes(b"db-bytes")
        (src / "avatars" / "1_1.png").write_bytes(b"a")
        db_copied, count = config.copy_local_data(str(self.tmp / "dst"), src_dir=src)
        self.assertTrue(db_copied)
        self.assertEqual(count, 1)
        self.assertTrue((self.tmp / "dst" / "loverlist.db").exists())
        self.assertTrue((self.tmp / "dst" / "avatars" / "1_1.png").exists())


class SetupFlowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        (self.tmp / "blocker.txt").write_text("x", encoding="utf-8")
        self.bad_dir = str(self.tmp / "blocker.txt" / "sub")   # 该路径必然不可创建
        patcher = mock.patch.object(config, "CONFIG_PATH", self.tmp / "data.ini")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = create_app(setup_error="无法访问该位置(测试)")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_guard_redirects_all_pages_to_setup(self):
        r = self.client.get("/persons")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/setup", r.headers["Location"])
        page = self.client.get("/setup")
        self.assertEqual(page.status_code, 200)
        self.assertIn("数据位置设置".encode("utf-8"), page.data)
        self.assertIn("无法访问该位置(测试)".encode("utf-8"), page.data)

    def test_setup_save_hot_switches(self):
        good = self.tmp / "data"
        r = self.client.post("/setup", data={"data_dir": str(good)}, follow_redirects=True)
        self.assertIn("数据位置已设置".encode("utf-8"), r.data)
        self.assertEqual(self.app.config["DB_PATH"], str(good / "loverlist.db"))
        self.assertEqual(config.load_data_dir(), str(good))      # data.ini 已写入
        self.assertIsNone(self.app.config["SETUP_ERROR"])
        self.assertEqual(self.client.get("/persons").status_code, 200)

    def test_setup_copy_local_data(self):
        import sqlite3
        src = self.tmp / "local"
        (src / "avatars").mkdir(parents=True)
        src_db = sqlite3.connect(str(src / "loverlist.db"))
        src_db.execute("CREATE TABLE IF NOT EXISTS t (x)")   # 真实的空 SQLite 库
        src_db.commit()
        src_db.close()
        (src / "avatars" / "1_x.png").write_bytes(b"a")
        p1 = mock.patch.object(config, "DEFAULT_DATA_DIR", src)
        p1.start()
        self.addCleanup(p1.stop)
        good = self.tmp / "data2"
        r = self.client.post(
            "/setup",
            data={"data_dir": str(good), "copy_local": "1"},
            follow_redirects=True,
        )
        self.assertIn("头像 1 个".encode("utf-8"), r.data)
        self.assertTrue((good / "loverlist.db").exists())
        self.assertTrue((good / "avatars" / "1_x.png").exists())

    def test_setup_invalid_path_rejected(self):
        r = self.client.post("/setup", data={"data_dir": self.bad_dir}, follow_redirects=True)
        self.assertIn("无法访问该位置".encode("utf-8"), r.data)
        self.assertIsNone(config.load_data_dir())               # 失败不写配置


if __name__ == "__main__":
    unittest.main()