"""业务逻辑层:全部函数以 sqlite3.Connection 作为第一个参数,便于复用与单元测试。"""
import math
import random
import re
import sqlite3
from datetime import date

# ---------------------------------------------------------------------------
# 常量与软校验
# ---------------------------------------------------------------------------
CODE_RE = re.compile(r"^[A-Z0-9]+-\d{3,4}$")   # 番号建议格式,如 LOV-123
BIRTH_RE = re.compile(r"^\d{4}-\d{2}$")        # 出生年月 YYYY-MM

ROLE_CHOICES = ["出演", "主演", "配角", "客串", "导演", "编剧", "配音", "制作"]

SORT_OPTIONS = {
    "heart":  "p.heart_count DESC, p.id DESC",
    "name":   "p.name ASC, p.id ASC",
    "height": "p.height DESC, p.id DESC",
    "birth":  "p.birth_ym DESC, p.id DESC",
}

# 当前事务所子查询:无结束年(至今)优先,否则取最近一段
_CURRENT_AGENCY_SQL = (
    "(SELECT ah.agency_name FROM agency_history ah"
    " WHERE ah.person_id = p.id"
    " ORDER BY (ah.end_year IS NULL) DESC, ah.start_year DESC, ah.id DESC"
    " LIMIT 1) AS current_agency"
)


def check_code(code) -> bool:
    """番号是否符合建议格式(仅用于 UI 提示,不拦截保存)。"""
    return bool(CODE_RE.match(code or ""))


def check_birth_ym(value) -> bool:
    return bool(BIRTH_RE.match(value or ""))


def _int_or_none(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 人物
# ---------------------------------------------------------------------------
def list_persons(conn, q="", agency=None, gender=None, sort="heart", page=1, per_page=20):
    """返回 (rows, total, page, pages)。支持姓名/别名/假名模糊搜索、事务所/性别筛选。"""
    where, params = [], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(p.name LIKE ? OR p.alias LIKE ? OR p.kana LIKE ?)")
        params += [like, like, like]
    if agency:
        where.append("p.id IN (SELECT person_id FROM agency_history WHERE agency_name LIKE ?)")
        params.append(f"%{agency.strip()}%")
    if gender:
        where.append("p.gender = ?")
        params.append(gender)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    order_sql = SORT_OPTIONS.get(sort, SORT_OPTIONS["heart"])

    total = conn.execute(f"SELECT COUNT(*) FROM persons p{where_sql}", params).fetchone()[0]
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, int(page or 1)), pages)
    rows = conn.execute(
        f"SELECT p.*,{_CURRENT_AGENCY_SQL} FROM persons p{where_sql}"
        f" ORDER BY {order_sql} LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()
    return rows, total, page, pages


def get_person(conn, person_id):
    return conn.execute(
        f"SELECT p.*,{_CURRENT_AGENCY_SQL} FROM persons p WHERE p.id = ?", (person_id,)
    ).fetchone()


def person_agencies(conn, person_id):
    """事务所历史:现任(无结束年)在前。"""
    return conn.execute(
        "SELECT * FROM agency_history WHERE person_id = ?"
        " ORDER BY (end_year IS NULL) DESC, start_year ASC, id ASC",
        (person_id,),
    ).fetchall()


def person_works(conn, person_id):
    """该人物出演/参与的全部作品与角色。"""
    return conn.execute(
        "SELECT w.*, c.id AS credit_id, c.role, c.character_name"
        " FROM credits c JOIN works w ON w.id = c.work_id"
        " WHERE c.person_id = ? ORDER BY w.code ASC",
        (person_id,),
    ).fetchall()


def _person_tuple(data):
    return (
        (data.get("name") or "").strip(),
        (data.get("alias") or "").strip(),
        (data.get("kana") or "").strip(),
        (data.get("gender") or "").strip() or "女",
        (data.get("birth_ym") or "").strip(),
        _int_or_none(data.get("height")),
        _int_or_none(data.get("bust")),
        _int_or_none(data.get("waist")),
        _int_or_none(data.get("hip")),
        (data.get("cup") or "").strip(),
        (data.get("notes") or "").strip(),
    )


def create_person(conn, data, agencies=None):
    if not (data.get("name") or "").strip():
        raise ValueError("姓名必填")
    cur = conn.execute(
        "INSERT INTO persons (name, alias, kana, gender, birth_ym, height, bust, waist, hip, cup, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _person_tuple(data),
    )
    _replace_agencies(conn, cur.lastrowid, agencies)
    conn.commit()
    return cur.lastrowid


def update_person(conn, person_id, data, agencies=None):
    if not (data.get("name") or "").strip():
        raise ValueError("姓名必填")
    conn.execute(
        "UPDATE persons SET name = ?, alias = ?, kana = ?, gender = ?, birth_ym = ?,"
        " height = ?, bust = ?, waist = ?, hip = ?, cup = ?, notes = ? WHERE id = ?",
        _person_tuple(data) + (person_id,),
    )
    _replace_agencies(conn, person_id, agencies)
    conn.commit()


def _replace_agencies(conn, person_id, agencies):
    conn.execute("DELETE FROM agency_history WHERE person_id = ?", (person_id,))
    for a in agencies or []:
        name = (a.get("agency_name") or "").strip()
        if not name:
            continue
        conn.execute(
            "INSERT INTO agency_history (person_id, agency_name, start_year, end_year)"
            " VALUES (?, ?, ?, ?)",
            (person_id, name, _int_or_none(a.get("start_year")), _int_or_none(a.get("end_year"))),
        )


def delete_person(conn, person_id):
    conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    conn.commit()


def increment_heart(conn, person_id):
    """心动 +1,返回新值。"""
    cur = conn.execute(
        "UPDATE persons SET heart_count = heart_count + 1 WHERE id = ?", (person_id,)
    )
    if cur.rowcount == 0:
        raise LookupError(f"人物不存在: id={person_id}")
    conn.commit()
    return conn.execute(
        "SELECT heart_count FROM persons WHERE id = ?", (person_id,)
    ).fetchone()[0]


def toggle_favorite(conn, person_id):
    """收藏/取消收藏,返回新状态。"""
    cur = conn.execute(
        "UPDATE persons SET is_favorite = 1 - is_favorite WHERE id = ?", (person_id,)
    )
    if cur.rowcount == 0:
        raise LookupError(f"人物不存在: id={person_id}")
    conn.commit()
    return conn.execute(
        "SELECT is_favorite FROM persons WHERE id = ?", (person_id,)
    ).fetchone()[0]


def favorite_persons(conn):
    return conn.execute(
        "SELECT * FROM persons WHERE is_favorite = 1 ORDER BY heart_count DESC, id ASC"
    ).fetchall()


def all_persons_brief(conn):
    """用于作品页的人物下拉。"""
    return conn.execute(
        "SELECT id, name, kana FROM persons ORDER BY name ASC, id ASC"
    ).fetchall()


# ---------------------------------------------------------------------------
# 作品与标签
# ---------------------------------------------------------------------------
def normalize_code(code) -> str:
    return (code or "").strip().upper()


def list_works(conn, q="", tag=None, page=1, per_page=20):
    """返回 (rows, total, page, pages)。rows 附带 tags 串与阵容人数 cast_size。"""
    where, params = [], []
    if q:
        like = f"%{q.strip()}%"
        where.append("(w.code LIKE ? OR w.title LIKE ?)")
        params += [like, like]
    if tag:
        where.append("w.id IN (SELECT work_id FROM work_tags WHERE tag = ?)")
        params.append(tag.strip())
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM works w{where_sql}", params).fetchone()[0]
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, int(page or 1)), pages)
    rows = conn.execute(
        "SELECT w.*,"
        " (SELECT GROUP_CONCAT(wt.tag, ',') FROM work_tags wt WHERE wt.work_id = w.id) AS tags,"
        " (SELECT COUNT(*) FROM credits c WHERE c.work_id = w.id) AS cast_size"
        f" FROM works w{where_sql}"
        " ORDER BY w.created_at DESC, w.id DESC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()
    return rows, total, page, pages


def get_work(conn, work_id):
    return conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()


def work_tags(conn, work_id):
    return [r[0] for r in conn.execute(
        "SELECT tag FROM work_tags WHERE work_id = ? ORDER BY id ASC", (work_id,)
    ).fetchall()]


def _split_tags(raw):
    seen, out = set(), []
    for part in re.split(r"[,，;；]+", raw or ""):
        part = part.strip()
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out


def _replace_tags(conn, work_id, tags):
    conn.execute("DELETE FROM work_tags WHERE work_id = ?", (work_id,))
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO work_tags (work_id, tag) VALUES (?, ?)", (work_id, tag)
        )


def create_work(conn, data, tags_raw=""):
    code = normalize_code(data.get("code"))
    if not code:
        raise ValueError("番号必填")
    cur = conn.execute(
        "INSERT INTO works (code, title, filename, status, notes) VALUES (?, ?, ?, ?, ?)",
        (
            code,
            (data.get("title") or "").strip(),
            (data.get("filename") or "").strip(),
            (data.get("status") or "").strip(),
            (data.get("notes") or "").strip(),
        ),
    )
    _replace_tags(conn, cur.lastrowid, _split_tags(tags_raw))
    conn.commit()
    return cur.lastrowid


def update_work(conn, work_id, data, tags_raw=""):
    code = normalize_code(data.get("code"))
    if not code:
        raise ValueError("番号必填")
    conn.execute(
        "UPDATE works SET code = ?, title = ?, filename = ?, status = ?, notes = ? WHERE id = ?",
        (
            code,
            (data.get("title") or "").strip(),
            (data.get("filename") or "").strip(),
            (data.get("status") or "").strip(),
            (data.get("notes") or "").strip(),
            work_id,
        ),
    )
    _replace_tags(conn, work_id, _split_tags(tags_raw))
    conn.commit()


def delete_work(conn, work_id):
    conn.execute("DELETE FROM works WHERE id = ?", (work_id,))
    conn.commit()


def all_tags(conn):
    """标签云: [(tag, cnt)],按出现次数降序。"""
    return conn.execute(
        "SELECT tag, COUNT(*) AS cnt FROM work_tags GROUP BY tag ORDER BY cnt DESC, tag ASC"
    ).fetchall()


# ---------------------------------------------------------------------------
# 阵容关联(人物 <-> 作品)
# ---------------------------------------------------------------------------
def work_credits(conn, work_id):
    """作品全阵容。"""
    return conn.execute(
        "SELECT c.id, c.role, c.character_name, p.id AS person_id, p.name AS person_name,"
        " p.kana AS person_kana, p.heart_count AS person_hearts"
        " FROM credits c JOIN persons p ON p.id = c.person_id"
        " WHERE c.work_id = ? ORDER BY c.id ASC",
        (work_id,),
    ).fetchall()


def add_credit(conn, work_id, person_id, role="", character_name=""):
    """添加阵容,返回 (credit_id, err)。同一人物同一关系类型不可重复。"""
    role = (role or "").strip() or "出演"
    try:
        cur = conn.execute(
            "INSERT INTO credits (person_id, work_id, role, character_name) VALUES (?, ?, ?, ?)",
            (person_id, work_id, role, (character_name or "").strip()),
        )
    except sqlite3.IntegrityError:
        return None, "该人物在本作品中已存在相同关系类型"
    conn.commit()
    return cur.lastrowid, ""


def remove_credit(conn, credit_id):
    conn.execute("DELETE FROM credits WHERE id = ?", (credit_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# 统计与今日心动
# ---------------------------------------------------------------------------
def dashboard_stats(conn):
    def one(sql):
        return conn.execute(sql).fetchone()[0]

    return {
        "person_count": one("SELECT COUNT(*) FROM persons"),
        "work_count": one("SELECT COUNT(*) FROM works"),
        "tag_count": one("SELECT COUNT(DISTINCT tag) FROM work_tags"),
        "total_hearts": one("SELECT COALESCE(SUM(heart_count), 0) FROM persons"),
    }


def top_persons(conn, limit=5):
    return conn.execute(
        "SELECT * FROM persons ORDER BY heart_count DESC, id ASC LIMIT ?", (limit,)
    ).fetchall()


def today_heart(conn):
    """今日心动:按心动指数加权随机,当天内确定(种子=日期),次日重抽。"""
    rows = conn.execute("SELECT * FROM persons").fetchall()
    if not rows:
        return None
    weights = [max(int(r["heart_count"] or 0), 0) for r in rows]
    rnd = random.Random(f"loverlist-{date.today().isoformat()}")
    if sum(weights) > 0:
        return rnd.choices(rows, weights=weights, k=1)[0]
    return rnd.choice(rows)