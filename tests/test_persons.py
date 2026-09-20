import unittest

from tests.helpers import make_conn, person_data
from loverlist import services


class PersonTests(unittest.TestCase):
    def setUp(self):
        make_conn(self)

    def test_create_requires_name(self):
        with self.assertRaises(ValueError):
            services.create_person(self.conn, person_data(name="  "))

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


if __name__ == "__main__":
    unittest.main()