import unittest

from tests.helpers import make_conn, person_data
from loverlist import services


class PersonTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_create_requires_name(self):
        with self.assertRaises(ValueError):
            services.create_person(self.conn, person_data(name="  "))

    def test_duplicate_name_rejected(self):
        services.create_person(self.conn, person_data())
        with self.assertRaises(ValueError):
            services.create_person(self.conn, person_data(alias="另一个别名"))
        # 首尾空格不影响重名判定
        with self.assertRaises(ValueError):
            services.create_person(self.conn, person_data(name=" 佐藤ひなた "))

    def test_update_name_conflict_rejected(self):
        services.create_person(self.conn, person_data(name="甲"))
        pid_b = services.create_person(self.conn, person_data(name="乙"))
        with self.assertRaises(ValueError):
            services.update_person(self.conn, pid_b, person_data(name="甲"))
        # 改回自己的名字(排除自身)不受影响
        services.update_person(self.conn, pid_b, person_data(name="乙", alias="乙儿"))
        self.assertEqual(services.get_person(self.conn, pid_b)["alias"], "乙儿")

    def test_create_with_agencies_and_current(self):
        agencies = [
            {"agency_name": "スターライン", "start_year": "2018", "end_year": ""},
            {"agency_name": "プラチナ", "start_year": "2016", "end_year": "2018"},
        ]
        pid = services.create_person(self.conn, person_data(), agencies)
        p = services.get_person(self.conn, pid)
        self.assertEqual(p["name"], "佐藤ひなた")
        self.assertEqual(p["gender"], "女")
        self.assertEqual(p["height"], 158)
        self.assertEqual(p["current_agency"], "スターライン")
        ags = services.person_agencies(self.conn, pid)
        self.assertEqual(
            [(a["agency_name"], a["end_year"]) for a in ags],
            [("スターライン", None), ("プラチナ", 2018)],
        )

    def test_update_replaces_agencies(self):
        pid = services.create_person(
            self.conn, person_data(),
            [{"agency_name": "A事务所", "start_year": "2000", "end_year": ""}],
        )
        services.update_person(
            self.conn, pid, person_data(name="新名字"),
            [{"agency_name": "B事务所", "start_year": "2001", "end_year": "2002"}],
        )
        ags = services.person_agencies(self.conn, pid)
        self.assertEqual([a["agency_name"] for a in ags], ["B事务所"])
        services.update_person(self.conn, pid, person_data(name="新名字"), [])
        self.assertEqual(services.person_agencies(self.conn, pid), [])

    def test_heart_and_favorite(self):
        pid = services.create_person(self.conn, person_data())
        self.assertEqual(services.increment_heart(self.conn, pid), 1)
        self.assertEqual(services.increment_heart(self.conn, pid), 2)
        self.assertEqual(services.toggle_favorite(self.conn, pid), 1)
        self.assertEqual(services.toggle_favorite(self.conn, pid), 0)

    def test_heart_missing_person(self):
        with self.assertRaises(LookupError):
            services.increment_heart(self.conn, 999)

    def test_delete_person(self):
        pid = services.create_person(self.conn, person_data())
        services.delete_person(self.conn, pid)
        self.assertIsNone(services.get_person(self.conn, pid))


class PersonListTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)
        self.a = services.create_person(
            self.conn, person_data(name="A", kana="えー"),
            [{"agency_name": "スターライン", "start_year": "2018", "end_year": ""}],
        )
        self.b = services.create_person(
            self.conn, person_data(name="B", alias="月亮"),
            [{"agency_name": "月光", "start_year": "2019", "end_year": "2020"}],
        )
        self.c = services.create_person(self.conn, person_data(name="C", gender="男"))
        self.conn.execute("UPDATE persons SET heart_count = 5 WHERE id = ?", (self.a,))
        self.conn.execute("UPDATE persons SET heart_count = 9 WHERE id = ?", (self.b,))
        self.conn.commit()

    def test_search_matches_alias_and_kana(self):
        rows, total, _, _ = services.list_persons(self.conn, q="月亮")
        self.assertEqual(total, 1)
        rows, total, _, _ = services.list_persons(self.conn, q="えー")
        self.assertEqual(total, 1)

    def test_filter_by_agency_and_gender(self):
        rows, total, _, _ = services.list_persons(self.conn, agency="スター")
        self.assertEqual(total, 1)
        rows, total, _, _ = services.list_persons(self.conn, gender="男")
        self.assertEqual([r["name"] for r in rows], ["C"])

    def test_sort_and_paging(self):
        rows, total, page, pages = services.list_persons(self.conn, sort="heart", per_page=2)
        self.assertEqual((total, page, pages), (3, 1, 2))
        self.assertEqual(rows[0]["name"], "B")
        rows, _, page, _ = services.list_persons(self.conn, sort="heart", page=2, per_page=2)
        self.assertEqual((page, rows[0]["name"]), (2, "C"))


class PersonAgeAliasSortTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_age_from_birth_ym(self):
        from datetime import date
        self.assertIsNone(services.age_from_birth_ym(""))
        self.assertIsNone(services.age_from_birth_ym("abc"))
        self.assertEqual(services.age_from_birth_ym("1990-06", today=date(2026, 9, 20)), 36)
        self.assertEqual(services.age_from_birth_ym("1990-09", today=date(2026, 9, 20)), 36)
        self.assertEqual(services.age_from_birth_ym("1990-10", today=date(2026, 9, 20)), 35)

    def test_normalize_alias(self):
        self.assertEqual(services.normalize_alias(" a,b;c、d ，e "), "a、b、c、d、e")
        self.assertEqual(services.normalize_alias(""), "")
        pid = services.create_person(self.conn, person_data(alias="ひな, 太阳"))
        self.assertEqual(services.get_person(self.conn, pid)["alias"], "ひな、太阳")

    def test_sort_cup_with_dir_and_empty_last(self):
        services.create_person(self.conn, person_data(name="A", birth_ym="1990-01", cup="A"))
        services.create_person(self.conn, person_data(name="F", birth_ym="1992-01", cup="F"))
        services.create_person(self.conn, person_data(name="N", birth_ym="1994-01", cup=""))
        rows, _, _, _ = services.list_persons(self.conn, sort="cup", dir="desc")
        self.assertEqual([r["name"] for r in rows], ["F", "A", "N"])
        rows, _, _, _ = services.list_persons(self.conn, sort="cup", dir="asc")
        self.assertEqual([r["name"] for r in rows], ["A", "F", "N"])

    def test_sort_birth_dir(self):
        services.create_person(self.conn, person_data(name="老", birth_ym="1990-01"))
        services.create_person(self.conn, person_data(name="少", birth_ym="2005-01"))
        rows, _, _, _ = services.list_persons(self.conn, sort="birth", dir="desc")
        self.assertEqual([r["name"] for r in rows], ["老", "少"])  # 年龄降序=年长在前
        rows, _, _, _ = services.list_persons(self.conn, sort="birth", dir="asc")
        self.assertEqual([r["name"] for r in rows], ["少", "老"])


if __name__ == "__main__":
    unittest.main()