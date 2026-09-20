import csv
import io
import unittest

from loverlist import csvio, services

from tests.helpers import make_conn, person_data


class AgencyFormatTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_format_and_parse_roundtrip(self):
        pid = services.create_person(self.conn, person_data(), [
            {"agency_name": "スターライン", "start_year": "2018", "end_year": ""},
            {"agency_name": "プラチナ", "start_year": "2016", "end_year": "2018"},
        ])
        text = csvio.format_agencies(services.person_agencies(self.conn, pid))
        self.assertEqual(text, "2018-至今: スターライン;2016-2018: プラチナ")
        ags = csvio.parse_agencies(text)
        self.assertEqual(ags[0], {"agency_name": "スターライン", "start_year": 2018, "end_year": None})
        self.assertEqual(ags[1], {"agency_name": "プラチナ", "start_year": 2016, "end_year": 2018})

    def test_parse_free_text(self):
        ags = csvio.parse_agencies("某某事务所")
        self.assertEqual(ags[0]["agency_name"], "某某事务所")
        self.assertEqual(csvio.parse_agencies(""), [])


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)
        self.pid = services.create_person(
            self.conn, person_data(name="ひなた"),
            [{"agency_name": "A社", "start_year": "2018", "end_year": ""}],
        )
        services.increment_heart(self.conn, self.pid)
        self.wid = services.create_work(self.conn, {"code": "LOV-001", "title": "初夏"}, "恋爱")
        services.add_credit(self.conn, self.wid, self.pid, "出演", "小夏")

    def test_export_all_kinds(self):
        for which in ("persons", "works", "credits"):
            self.assertTrue(csvio.export_csv_string(self.conn, which))
        with self.assertRaises(ValueError):
            csvio.export_csv_string(self.conn, "nope")

    def test_persons_import_updates_but_keeps_hearts(self):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(csvio.PERSON_HEADERS)
        w.writerow(["ひなた", "新的别名", "さとうひなた", "女", "1998-04", "159",
                    "86", "58", "85", "F", "99", "1", "备注改了", "2019-至今: B社"])
        w.writerow(["", "", "", "", "", "", "", "", "", "", "", "", "", ""])
        buf.seek(0)
        stats = csvio.import_csv(self.conn, "persons", buf)
        self.assertEqual(stats, {"created": 0, "updated": 1, "skipped": 1})
        p = services.get_person(self.conn, self.pid)
        self.assertEqual(p["alias"], "新的别名")
        self.assertEqual(p["heart_count"], 1)  # 心动不被覆盖
        self.assertEqual(services.person_agencies(self.conn, self.pid)[0]["agency_name"], "B社")

    def test_works_import_create_and_update(self):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(csvio.WORK_HEADERS)
        w.writerow(["lov-002", "新作", "悬疑,恐怖", "", "待看", ""])
        w.writerow(["LOV-001", "初夏改版", "恋爱,青春", "", "", "改"])
        buf.seek(0)
        stats = csvio.import_csv(self.conn, "works", buf)
        self.assertEqual(stats, {"created": 1, "updated": 1, "skipped": 0})
        wid2 = services.list_works(self.conn, q="LOV-002")[0][0]["id"]
        self.assertEqual(services.work_tags(self.conn, wid2), ["悬疑", "恐怖"])
        self.assertEqual(services.get_work(self.conn, self.wid)["title"], "初夏改版")

    def test_credits_import(self):
        services.create_person(self.conn, person_data(name="愛理"))
        services.create_work(self.conn, {"code": "LOV-002"})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(csvio.CREDIT_HEADERS)
        w.writerow(["ひなた", "LOV-001", "出演", "改名角色"])   # 更新
        w.writerow(["愛理", "lov-002", "", "ゲスト"])           # 新增(番号小写)
        w.writerow(["不存在的人", "LOV-001", "出演", ""])        # 跳过
        buf.seek(0)
        stats = csvio.import_csv(self.conn, "credits", buf)
        self.assertEqual((stats["created"], stats["updated"], stats["skipped"]), (1, 1, 1))
        credits = services.work_credits(self.conn, self.wid)
        self.assertEqual(credits[0]["character_name"], "改名角色")

    def test_full_roundtrip(self):
        texts = {k: csvio.export_csv_string(self.conn, k)
                 for k in ("persons", "works", "credits")}
        self.conn.execute("DELETE FROM persons")   # 级联清空 credits
        self.conn.execute("DELETE FROM works")
        self.conn.commit()
        s1 = csvio.import_csv(self.conn, "persons", io.StringIO(texts["persons"]))
        s2 = csvio.import_csv(self.conn, "works", io.StringIO(texts["works"]))
        s3 = csvio.import_csv(self.conn, "credits", io.StringIO(texts["credits"]))
        self.assertEqual((s1["created"], s2["created"], s3["created"]), (1, 1, 1))
        stats = services.dashboard_stats(self.conn)
        self.assertEqual(stats["person_count"], 1)
        self.assertEqual(stats["work_count"], 1)
        new_wid = self.conn.execute(
            "SELECT id FROM works WHERE code = 'LOV-001'"
        ).fetchone()["id"]
        self.assertEqual(services.work_tags(self.conn, new_wid), ["恋爱"])


    def test_status_import_normalization(self):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(csvio.WORK_HEADERS)
        w.writerow(["LOV-010", "原样已收录", "恋爱", "", "已收录", ""])
        w.writerow(["LOV-011", "未知归评审", "剧情", "", "随便写的", ""])
        w.writerow(["LOV-012", "空归评审", "", "", "", ""])
        w.writerow(["LOV-001", "更新并改状态", "", "", "已收录", ""])
        buf.seek(0)
        stats = csvio.import_csv(self.conn, "works", buf)
        self.assertEqual((stats["created"], stats["updated"], stats["skipped"]), (3, 1, 0))

        def status_of(code):
            return self.conn.execute(
                "SELECT status FROM works WHERE code = ?", (code,)
            ).fetchone()["status"]

        self.assertEqual(status_of("LOV-010"), "已收录")
        self.assertEqual(status_of("LOV-011"), "评审中")
        self.assertEqual(status_of("LOV-012"), "评审中")
        self.assertEqual(status_of("LOV-001"), "已收录")


    def test_vr_column_roundtrip(self):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(csvio.WORK_HEADERS)
        w.writerow(["LOV-020", "VR作品", "悬疑", "", "评审中", "是", ""])
        w.writerow(["LOV-021", "普通作品", "", "", "已收录", "", ""])
        buf.seek(0)
        csvio.import_csv(self.conn, "works", buf)

        def vr_of(code):
            return self.conn.execute(
                "SELECT is_vr FROM works WHERE code = ?", (code,)
            ).fetchone()["is_vr"]

        self.assertEqual(vr_of("LOV-020"), 1)
        self.assertEqual(vr_of("LOV-021"), 0)
        # 导出包含 VR 列与「是」标记
        text = csvio.export_csv_string(self.conn, "works")
        first_line = text.splitlines()[0]
        self.assertIn("VR", first_line)
        self.assertIn("是", text)


if __name__ == "__main__":
    unittest.main()