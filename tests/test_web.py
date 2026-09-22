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
        self.assertIn('name="code_alpha" id="work-code-alpha" required placeholder="LOV" value="LOV"', html)
        self.assertIn('name="code_num" id="work-code-num" required placeholder="007" value="007"', html)

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
        # 详情页改为实时搜索:含搜索框与内嵌人物JSON,不再有旧下拉
        page = self.client.get(f"/works/{wid}")
        self.assertIn(b'id="person-search"', page.data)
        self.assertIn(b'id="persons-data"', page.data)
        self.assertIn("ひなた".encode("utf-8"), page.data)   # 人物JSON已内嵌
        self.assertNotIn(b'<select name="person_id"', page.data)
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

    def test_heart_button_scopes_and_copy_button(self):
        # 心动+1 按钮:仅人物列表/人物详情/作品详情;其他页面纯展示
        self.client.post("/persons", data={"name": "ひなた"})
        self.client.post(
            "/works",
            data={"code_alpha": "LOV", "code_num": "001"},
        )
        conn = get_connection(self.db_path)
        try:
            pid = conn.execute("SELECT id FROM persons LIMIT 1").fetchone()[0]
            wid = conn.execute("SELECT id FROM works LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        self.client.post(
            f"/works/{wid}/credits",
            data={"person_id": str(pid), "role": "", "character_name": ""},
        )
        persons_html = self.client.get("/persons").data
        self.assertNotIn(b"heart-btn js-heart", persons_html)   # /persons 心动改纯展示
        self.assertIn(b"heart-badge", persons_html)
        self.assertIn(b"heart-btn js-heart", self.client.get(f"/persons/{pid}").data)
        work_html = self.client.get(f"/works/{wid}").data
        self.assertIn(b"heart-btn js-heart", work_html)             # 阵容表可+1
        self.assertIn(b"data-copy", work_html)                      # 复制按钮
        self.assertIn("LOV-001@ひなた".encode("utf-8"), work_html)   # 文件名自动派生
        self.assertIn(b"filename-text", work_html)                  # 超长省略容器
        self.assertNotIn(b"heart-btn js-heart", self.client.get("/").data)        # 仪表盘纯展示
        self.assertNotIn(b"heart-btn js-heart", self.client.get("/favorites").data)  # 心动向纯展示
        self.assertIn(b"heart-badge", self.client.get("/").data)
        # 表单不再有文件名输入(自动派生)
        self.assertNotIn(b'name="filename"', self.client.get(f"/works/{wid}/edit").data)
        # 移除阵容 → 文件名自动重算(仅剩番号)
        conn = get_connection(self.db_path)
        try:
            cid = conn.execute("SELECT id FROM credits LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        self.client.post(f"/credits/{cid}/delete", data={"work_id": str(wid)})
        work_html = self.client.get(f"/works/{wid}").data
        self.assertNotIn("LOV-001@ひなた".encode("utf-8"), work_html)
        self.assertIn(b"data-copy", work_html)

    def test_works_tag_collapse_markup(self):
        # 演示库标签少于阈值:不出现折叠按钮(JS 源码含 tag-toggle 字样,断言按钮专属 id 属性)
        r = self.client.get("/works")
        self.assertNotIn(b'id="tag-toggle"', r.data)
        # 灌入 25 个标签的作品 → 出现折叠按钮且容器带 collapsed 类
        conn = get_connection(self.db_path)
        try:
            services.create_work(
                conn, {"code": "LOV-099", "title": "标签墙"},
                ",".join(f"标签{i:02d}" for i in range(1, 26)),
            )
        finally:
            conn.close()
        r = self.client.get("/works")
        self.assertIn(b'id="tag-toggle"', r.data)
        self.assertIn(b"tag-cloud collapsed", r.data)
        self.assertIn("展开全部 25 个标签".encode("utf-8"), r.data)
        # 带 tag 筛选时不折叠
        r = self.client.get("/works", query_string={"tag": "标签01"})
        self.assertNotIn(b"tag-cloud collapsed", r.data)

    def test_review_page_flow(self):
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001", "title": "待审"})
        # 导航角标:待审 1
        self.assertIn(b"nav-badge", self.client.get("/works").data)
        r = self.client.get("/review")
        self.assertIn("待评审".encode("utf-8"), r.data)
        self.assertIn(b"LOV-001", r.data)
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works WHERE code = 'LOV-001'").fetchone()[0]
        finally:
            conn.close()
        # 标记已收录 → 移入已判定,待审清零
        r = self.client.post(f"/works/{wid}/status", data={"status": "已收录"}, follow_redirects=True)
        self.assertIn("状态已更新".encode("utf-8"), r.data)
        r = self.client.get("/review")
        self.assertNotIn(b"nav-badge", r.data)
        self.assertIn("已判定".encode("utf-8"), r.data)
        # /works 状态筛选
        r = self.client.get("/works", query_string={"status": "已收录"})
        self.assertIn(b"LOV-001", r.data)
        r = self.client.get("/works", query_string={"status": "评审中"})
        self.assertNotIn(b"LOV-001", r.data)
        # 退回评审 + 非法状态被拒
        self.client.post(f"/works/{wid}/status", data={"status": "评审中"})
        self.assertIn(b"LOV-001", self.client.get("/review").data)
        r = self.client.post(f"/works/{wid}/status", data={"status": "xx"}, follow_redirects=True)
        self.assertIn("未知的状态值".encode("utf-8"), r.data)

    def test_persons_page_age_and_alias_chips(self):
        self.client.post("/persons", data={"name": "ひなた", "alias": "ひな,太阳", "birth_ym": "1998-04"})
        r = self.client.get("/persons")
        html = r.data
        self.assertNotIn("<th>别名 / 假名</th>".encode("utf-8"), html)   # 列表不再展示别名/假名列
        self.assertIn("年龄".encode("utf-8"), html)
        self.assertIn("岁".encode("utf-8"), html)
        # 详情页:别名以标签列表展示,并有年龄行
        r = self.client.get("/persons/1")
        self.assertIn('<span class="chip">ひな</span>'.encode("utf-8"), r.data)
        self.assertIn('<span class="chip">太阳</span>'.encode("utf-8"), r.data)
        self.assertIn("年龄".encode("utf-8"), r.data)
        # 表单不再有状态字段;新建作品默认进入评审页
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001"})
        self.assertNotIn(b'name="status"', self.client.get("/works/new").data)
        self.assertIn(b"LOV-001", self.client.get("/review").data)

    def test_vr_mark_and_status_cards_on_pages(self):
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001", "is_vr": "1"})
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "002"})
        # /works:VR 作品番号旁出现且仅出现一个 ᯅ
        r = self.client.get("/works")
        self.assertEqual(r.data.count("ᯅ".encode("utf-8")), 1)
        # 详情页番号旁也有 ᯅ;编辑表单勾选回显
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works WHERE code = 'LOV-001'").fetchone()[0]
        finally:
            conn.close()
        self.assertIn("ᯅ".encode("utf-8"), self.client.get(f"/works/{wid}").data)
        self.assertIn(b"checked", self.client.get(f"/works/{wid}/edit").data)
        self.assertNotIn(b"checked", self.client.get("/works/new").data.replace(b'name="is_vr" value="1"', b""))
        # 仪表盘状态统计卡
        r = self.client.get("/")
        for word in ("待审", "已收录", "不予收录"):
            self.assertIn(word.encode("utf-8"), r.data)

    def test_favorites_page(self):
        r = self.client.get("/favorites")
        self.assertEqual(r.status_code, 200)
        self.assertIn("心动榜".encode("utf-8"), r.data)

    def test_duplicate_person_name_web(self):
        self.client.post("/persons", data={"name": "ひなた"})
        r = self.client.post(
            "/persons", data={"name": "ひなた", "alias": "太阳", "kana": "ヒナタ"}
        )
        # 不重定向:原地重渲表单,给出错误并保留已填内容
        self.assertEqual(r.status_code, 200)
        self.assertIn("已存在同名人物".encode("utf-8"), r.data)
        self.assertIn('value="太阳"'.encode("utf-8"), r.data)
        self.assertIn('value="ひなた"'.encode("utf-8"), r.data)
        conn = get_connection(self.db_path)
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(cnt, 1)

    def test_person_rename_conflict_web(self):
        self.client.post("/persons", data={"name": "甲"})
        self.client.post("/persons", data={"name": "乙"})
        pid = self._first_person_id()
        conn = get_connection(self.db_path)
        try:
            name = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()[0]
        finally:
            conn.close()
        other = "甲" if name == "乙" else "乙"
        r = self.client.post(f"/persons/{pid}", data={"name": other})
        self.assertEqual(r.status_code, 200)
        self.assertIn("已存在同名人物".encode("utf-8"), r.data)

    def test_duplicate_work_code_web(self):
        self.client.post("/works", data={"code_alpha": "lov", "code_num": "1"})
        r = self.client.post(
            "/works",
            data={"code_alpha": "LOV", "code_num": "001", "title": "重复的作品", "tags": "恋爱"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("番号 LOV-001 已存在".encode("utf-8"), r.data)
        self.assertIn('value="重复的作品"'.encode("utf-8"), r.data)
        self.assertIn('value="恋爱"'.encode("utf-8"), r.data)

    def test_work_update_code_conflict_web(self):
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001"})
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "002"})
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works WHERE code = 'LOV-002'").fetchone()[0]
        finally:
            conn.close()
        r = self.client.post(f"/works/{wid}", data={"code_alpha": "LOV", "code_num": "001"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("番号 LOV-001 已存在".encode("utf-8"), r.data)

    def test_person_dup_check_api(self):
        self.client.post("/persons", data={"name": "ひなた"})
        # 命中:返回重复标记与已有记录链接
        d = self.client.get("/persons/dup-check", query_string={"q": "ひなた"}).get_json()
        self.assertTrue(d["duplicate"])
        self.assertIn("已存在同名人物", d["label"])
        self.assertIn("/persons/", d["url"])
        # 首尾空格不影响判定;未命中返回 duplicate=false
        self.assertTrue(self.client.get(
            "/persons/dup-check", query_string={"q": " ひなた "}).get_json()["duplicate"])
        self.assertFalse(self.client.get(
            "/persons/dup-check", query_string={"q": "存在しない"}).get_json()["duplicate"])
        # 空姓名:不提示
        self.assertFalse(self.client.get(
            "/persons/dup-check", query_string={"q": ""}).get_json()["duplicate"])
        # 编辑态排除自身
        pid = self._first_person_id()
        d = self.client.get(
            "/persons/dup-check", query_string={"q": "ひなた", "exclude_id": str(pid)}
        ).get_json()
        self.assertFalse(d["duplicate"])

    def test_work_dup_check_api(self):
        self.client.post("/works", data={"code_alpha": "lov", "code_num": "1"})
        # 小写/未补零输入同样命中(与提交时归一口径一致)
        d = self.client.get(
            "/works/dup-check", query_string={"alpha": "LOV", "num": "001"}
        ).get_json()
        self.assertTrue(d["duplicate"])
        self.assertEqual(d["label"], "番号 LOV-001 已存在")
        self.assertIn("/works/", d["url"])
        # 未命中 / 段不完整:均返回 duplicate=false
        self.assertFalse(self.client.get(
            "/works/dup-check", query_string={"alpha": "LOV", "num": "002"}).get_json()["duplicate"])
        self.assertFalse(self.client.get(
            "/works/dup-check", query_string={"alpha": "", "num": "001"}).get_json()["duplicate"])
        self.assertFalse(self.client.get(
            "/works/dup-check", query_string={"alpha": "LOV", "num": "abc"}).get_json()["duplicate"])
        # 编辑态排除自身
        conn = get_connection(self.db_path)
        try:
            wid = conn.execute("SELECT id FROM works LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        d = self.client.get(
            "/works/dup-check",
            query_string={"alpha": "LOV", "num": "001", "exclude_id": str(wid)},
        ).get_json()
        self.assertFalse(d["duplicate"])

    def test_nav_create_buttons_and_copy_name(self):
        # 导航栏:全局可见的新建人物/新建作品入口
        html = self.client.get("/").data.decode("utf-8")
        self.assertIn('href="/persons/new"', html)
        self.assertIn('href="/works/new"', html)
        # 旧位置(列表页 page-head)不再保留新建按钮(空列表提示文字不受影响)
        self.assertNotIn(
            '<a class="btn btn-primary" href="/persons/new">',
            self.client.get("/persons").data.decode("utf-8"),
        )
        self.assertNotIn(
            '<a class="btn btn-primary" href="/works/new">',
            self.client.get("/works").data.decode("utf-8"),
        )
        # /persons 与首页(今日心动 + Top5)的人名旁均有复制按钮
        self.client.post("/persons", data={"name": "ひなた"})
        html = self.client.get("/persons").data.decode("utf-8")
        self.assertIn('class="btn btn-small btn-ghost js-copy copy-name"', html)
        self.assertIn('data-copy="ひなた"', html)
        html = self.client.get("/").data.decode("utf-8")
        self.assertIn('data-copy="ひなた"', html)

    def test_dashboard_today_review_card(self):
        self.client.post("/persons", data={"name": "ひなた"})
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "001", "is_vr": "1"})
        self.client.post("/works", data={"code_alpha": "LOV", "code_num": "002"})
        conn = get_connection(self.db_path)
        try:
            pid = conn.execute("SELECT id FROM persons LIMIT 1").fetchone()[0]
            wid = conn.execute("SELECT id FROM works WHERE code = 'LOV-001'").fetchone()[0]
            services.add_credit(conn, wid, pid, "出演", "")
        finally:
            conn.close()
        html = self.client.get("/").data.decode("utf-8")
        self.assertIn("今日评审", html)
        self.assertIn("LOV-001", html)
        self.assertIn("LOV-002", html)
        self.assertIn('data-copy="LOV-001@ひなた"', html)   # 文件名复制按钮
        self.assertIn('data-copy="LOV-002"', html)

    def test_review_page_compact_limited_newest_first_vr_mark(self):
        for i in range(1, 12):
            self.client.post(
                "/works", data={"code_alpha": "LOV", "code_num": f"{i:03d}"},
                follow_redirects=True,
            )
        self.client.post(
            "/works", data={"code_alpha": "LOV", "code_num": "100", "is_vr": "1"},
            follow_redirects=True,
        )
        html = self.client.get("/review").data.decode("utf-8")
        # 最新加入的排在最前
        self.assertLess(html.index("LOV-100"), html.index("LOV-001"))
        # 限量:12 条待评审默认只展开 10 行,其余折叠 + 展开按钮
        self.assertEqual(html.count('class="review-row'), 12)
        self.assertEqual(html.count("hidden-extra"), 2)
        self.assertIn("显示全部 12 条", html)
        # VR 作品带 ᯅ 标记
        self.assertIn("ᯅ", html)


if __name__ == "__main__":
    unittest.main()