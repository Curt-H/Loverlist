"""CSV 导入导出:UTF-8-SIG 编码、中文表头、存在即更新。

约定:
- 人物 persons.csv:姓名/别名/假名/性别/出生年月/身高/胸围/腰围/臀围/罩杯/心动指数/收藏/备注/事务所历史
- 作品 works.csv:番号/标题/风格TAG/文件名/状态/备注
- 阵容 credits.csv:人物姓名/作品番号/关系类型/角色名
- 事务所历史在单元格内多段用「;」分隔,段格式 `2018-至今: XX事务所`
- 导入不覆盖心动指数与收藏(它们由应用内的点击行为驱动)
"""
import csv
import io
import re

from . import services

AGENCY_SEP = ";"
AGENCY_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4}|至今|现在|今)\s*[:：]\s*(.+?)\s*$")

PERSON_HEADERS = ["姓名", "别名", "假名", "性别", "出生年月", "身高", "胸围", "腰围",
                  "臀围", "罩杯", "心动指数", "收藏", "备注", "事务所历史"]
WORK_HEADERS = ["番号", "标题", "风格TAG", "文件名", "状态", "备注"]
CREDIT_HEADERS = ["人物姓名", "作品番号", "关系类型", "角色名"]


# ---------------------------------------------------------------------------
# 事务所历史的 文本 <-> 结构
# ---------------------------------------------------------------------------
def format_agencies(agency_rows) -> str:
    parts = []
    for a in agency_rows:
        end = a["end_year"] if a["end_year"] is not None else "至今"
        parts.append(f"{a['start_year'] or '?'}-{end}: {a['agency_name']}")
    return AGENCY_SEP.join(parts)


def parse_agencies(text):
    out = []
    for seg in (text or "").split(AGENCY_SEP):
        seg = seg.strip()
        if not seg:
            continue
        m = AGENCY_RE.match(seg)
        if m:
            start, end, name = m.group(1), m.group(2), m.group(3)
            out.append({
                "agency_name": name,
                "start_year": int(start),
                "end_year": int(end) if end.isdigit() else None,
            })
        else:
            out.append({"agency_name": seg, "start_year": None, "end_year": None})
    return out


def _to_int(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _row_val(row, key) -> str:
    v = row.get(key)
    return v.strip() if isinstance(v, str) else (v or "")


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
def export_csv_string(conn, which) -> str:
    """导出为 CSV 文本(不带 BOM,由下载端点统一加 UTF-8-SIG)。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    if which == "persons":
        writer.writerow(PERSON_HEADERS)
        for p in conn.execute("SELECT * FROM persons ORDER BY id").fetchall():
            writer.writerow([
                p["name"], p["alias"], p["kana"], p["gender"], p["birth_ym"],
                p["height"] if p["height"] is not None else "",
                p["bust"] if p["bust"] is not None else "",
                p["waist"] if p["waist"] is not None else "",
                p["hip"] if p["hip"] is not None else "",
                p["cup"], p["heart_count"], p["is_favorite"], p["notes"],
                format_agencies(services.person_agencies(conn, p["id"])),
            ])
    elif which == "works":
        writer.writerow(WORK_HEADERS)
        for w in conn.execute("SELECT * FROM works ORDER BY id").fetchall():
            writer.writerow([
                w["code"], w["title"], ",".join(services.work_tags(conn, w["id"])),
                w["filename"], w["status"], w["notes"],
            ])
    elif which == "credits":
        writer.writerow(CREDIT_HEADERS)
        rows = conn.execute(
            "SELECT p.name AS person_name, w.code AS work_code, c.role, c.character_name"
            " FROM credits c"
            " JOIN persons p ON p.id = c.person_id"
            " JOIN works w ON w.id = c.work_id ORDER BY c.id"
        ).fetchall()
        for c in rows:
            writer.writerow([c["person_name"], c["work_code"], c["role"], c["character_name"]])
    else:
        raise ValueError(f"未知的导出类型: {which}")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 导入(存在即更新)
# ---------------------------------------------------------------------------
def import_persons(conn, text_stream):
    reader = csv.DictReader(text_stream)
    created = updated = skipped = 0
    for row in reader:
        name = _row_val(row, "姓名")
        if not name:
            skipped += 1
            continue
        data = {
            "name": name,
            "alias": _row_val(row, "别名"),
            "kana": _row_val(row, "假名"),
            "gender": _row_val(row, "性别") or "女",
            "birth_ym": _row_val(row, "出生年月"),
            "height": _to_int(_row_val(row, "身高")),
            "bust": _to_int(_row_val(row, "胸围")),
            "waist": _to_int(_row_val(row, "腰围")),
            "hip": _to_int(_row_val(row, "臀围")),
            "cup": _row_val(row, "罩杯"),
            "notes": _row_val(row, "备注"),
        }
        agencies = parse_agencies(_row_val(row, "事务所历史"))
        existing = conn.execute(
            "SELECT id FROM persons WHERE name = ? ORDER BY id LIMIT 1", (name,)
        ).fetchone()
        if existing:
            services.update_person(conn, existing["id"], data, agencies)
            updated += 1
        else:
            services.create_person(conn, data, agencies)
            created += 1
    return {"created": created, "updated": updated, "skipped": skipped}


def import_works(conn, text_stream):
    reader = csv.DictReader(text_stream)
    created = updated = skipped = 0
    for row in reader:
        code = services.normalize_code(_row_val(row, "番号"))
        if not code:
            skipped += 1
            continue
        data = {
            "code": code,
            "title": _row_val(row, "标题"),
            "filename": _row_val(row, "文件名"),
            "status": _row_val(row, "状态"),
            "notes": _row_val(row, "备注"),
        }
        tags_raw = _row_val(row, "风格TAG")
        existing = conn.execute(
            "SELECT id FROM works WHERE code = ?", (code,)
        ).fetchone()
        if existing:
            services.update_work(conn, existing["id"], data, tags_raw)
            updated += 1
        else:
            services.create_work(conn, data, tags_raw)
            created += 1
    return {"created": created, "updated": updated, "skipped": skipped}


def import_credits(conn, text_stream):
    reader = csv.DictReader(text_stream)
    created = updated = skipped = 0
    for row in reader:
        person_name = _row_val(row, "人物姓名")
        work_code = services.normalize_code(_row_val(row, "作品番号"))
        person = conn.execute(
            "SELECT id FROM persons WHERE name = ? ORDER BY id LIMIT 1", (person_name,)
        ).fetchone()
        work = conn.execute(
            "SELECT id FROM works WHERE code = ?", (work_code,)
        ).fetchone() if work_code else None
        if not person or not work:
            skipped += 1
            continue
        role = _row_val(row, "关系类型") or "出演"
        character = _row_val(row, "角色名")
        existing = conn.execute(
            "SELECT id FROM credits WHERE person_id = ? AND work_id = ? AND role = ?",
            (person["id"], work["id"], role),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE credits SET character_name = ? WHERE id = ?",
                (character, existing["id"]),
            )
            updated += 1
        else:
            services.add_credit(conn, work["id"], person["id"], role, character)
            created += 1
    conn.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def import_csv(conn, which, text_stream):
    """统一入口:which ∈ persons/works/credits,text_stream 为 CSV 文本流。"""
    if which == "persons":
        return import_persons(conn, text_stream)
    if which == "works":
        return import_works(conn, text_stream)
    if which == "credits":
        return import_credits(conn, text_stream)
    raise ValueError(f"未知的导入类型: {which}")