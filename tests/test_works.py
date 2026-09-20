import sqlite3
import unittest

from loverlist import services

from tests.helpers import make_conn, person_data


class BuildCodeTests(unittest.TestCase):
    def test_pads_uppercases_and_keeps_long_nums(self):
        self.assertEqual(services.build_code("lov", "7"), "LOV-007")
        self.assertEqual(services.build_code(" LOV ", "12"), "LOV-012")
        self.assertEqual(services.build_code("ABC", "123"), "ABC-123")
        self.assertEqual(services.build_code("ABC", "1234"), "ABC-1234")
        self.assertEqual(services.build_code("ABC", "12345"), "ABC-12345")

    def test_strips_non_digits(self):
        self.assertEqual(services.build_code("AB", "12a3"), "AB-123")

    def test_alpha_required(self):
        with self.assertRaises(ValueError):
            services.build_code("", "123")
        with self.assertRaises(ValueError):
            services.build_code("   ", "123")

    def test_num_required(self):
        with self.assertRaises(ValueError):
            services.build_code("LOV", "")
        with self.assertRaises(ValueError):
            services.build_code("LOV", "abc")


class WorkTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_create_normalizes_code_and_tags(self):
        wid = services.create_work(
            self.conn, {"code": " lov-001 ", "title": "初夏の恋人"}, "恋爱,青春,,恋爱"
        )
        w = services.get_work(self.conn, wid)
        self.assertEqual(w["code"], "LOV-001")
        self.assertEqual(services.work_tags(self.conn, wid), ["恋爱", "青春"])

    def test_code_required(self):
        with self.assertRaises(ValueError):
            services.create_work(self.conn, {"code": "  "})

    def test_duplicate_code_rejected(self):
        services.create_work(self.conn, {"code": "LOV-001"})
        with self.assertRaises(sqlite3.IntegrityError):
            services.create_work(self.conn, {"code": "lov-001"})

    def test_update_replaces_tags(self):
        wid = services.create_work(self.conn, {"code": "LOV-001"}, "恋爱")
        services.update_work(self.conn, wid, {"code": "LOV-001", "title": "新标题"}, "悬疑,剧情")
        self.assertEqual(services.work_tags(self.conn, wid), ["悬疑", "剧情"])

    def test_list_search_and_tag_filter(self):
        services.create_work(self.conn, {"code": "LOV-001", "title": "星空"}, "恋爱")
        services.create_work(self.conn, {"code": "LOV-002", "title": "大海"}, "剧情")
        rows, total, _, _ = services.list_works(self.conn, q="星空")
        self.assertEqual(total, 1)
        rows, total, _, _ = services.list_works(self.conn, tag="剧情")
        self.assertEqual([r["code"] for r in rows], ["LOV-002"])
        rows, total, _, _ = services.list_works(self.conn, q="lov-0")
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]["cast_size"], 0)

    def test_all_tags_counts(self):
        services.create_work(self.conn, {"code": "LOV-001"}, "恋爱,青春")
        services.create_work(self.conn, {"code": "LOV-002"}, "恋爱")
        tags = {r["tag"]: r["cnt"] for r in services.all_tags(self.conn)}
        self.assertEqual(tags, {"恋爱": 2, "青春": 1})


class CreditTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)
        self.pid = services.create_person(self.conn, person_data(name="ひなた"))
        self.wid = services.create_work(self.conn, {"code": "LOV-001", "title": "初夏"})

    def test_add_credit_defaults_and_listing(self):
        cid, err = services.add_credit(self.conn, self.wid, self.pid, "", "")
        self.assertEqual(err, "")
        credits = services.work_credits(self.conn, self.wid)
        self.assertEqual(credits[0]["person_name"], "ひなた")
        self.assertEqual(credits[0]["role"], "出演")

    def test_duplicate_credit_rejected(self):
        services.add_credit(self.conn, self.wid, self.pid, "出演", "小夏")
        cid, err = services.add_credit(self.conn, self.wid, self.pid, " 出演 ", "")
        self.assertIsNone(cid)
        self.assertTrue(err)

    def test_multiple_roles_allowed(self):
        services.add_credit(self.conn, self.wid, self.pid, "出演", "")
        cid, err = services.add_credit(self.conn, self.wid, self.pid, "导演", "")
        self.assertIsNotNone(cid)
        self.assertEqual(err, "")

    def test_remove_credit(self):
        cid, _ = services.add_credit(self.conn, self.wid, self.pid, "出演", "")
        services.remove_credit(self.conn, cid)
        self.assertEqual(services.work_credits(self.conn, self.wid), [])

    def test_person_works_and_cascade(self):
        services.add_credit(self.conn, self.wid, self.pid, "出演", "小夏")
        works = services.person_works(self.conn, self.pid)
        self.assertEqual(works[0]["code"], "LOV-001")
        services.delete_person(self.conn, self.pid)
        self.assertEqual(services.work_credits(self.conn, self.wid), [])


class StatsTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_empty_stats_and_today(self):
        self.assertEqual(
            services.dashboard_stats(self.conn),
            {"person_count": 0, "work_count": 0, "tag_count": 0, "total_hearts": 0},
        )
        self.assertIsNone(services.today_heart(self.conn))

    def test_stats_top_fav_and_weighted_today(self):
        pid_lo = services.create_person(self.conn, person_data(name="少动"))
        pid_hi = services.create_person(self.conn, person_data(name="超动"))
        for _ in range(10):
            services.increment_heart(self.conn, pid_hi)
        services.toggle_favorite(self.conn, pid_lo)
        stats = services.dashboard_stats(self.conn)
        self.assertEqual(stats["person_count"], 2)
        self.assertEqual(stats["total_hearts"], 10)
        self.assertEqual(services.top_persons(self.conn, 1)[0]["name"], "超动")
        favs = services.favorite_persons(self.conn)
        self.assertEqual([p["name"] for p in favs], ["少动"])
        pick = services.today_heart(self.conn)
        self.assertEqual(pick["name"], "超动")  # 权重 0:10,必中高权重
        self.assertEqual(services.today_heart(self.conn)["id"], pick["id"])  # 同日确定


if __name__ == "__main__":
    unittest.main()