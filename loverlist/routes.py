"""Web 路由:全中文界面,页面清单见 README。"""
import io
import sqlite3

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from . import csvio, demo, services

bp = Blueprint("loverlist", __name__)

GENDERS = ["女", "男", "其他"]


# ---------------------------------------------------------------------------
# 表单工具
# ---------------------------------------------------------------------------
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


def _page():
    return _int_or_none(request.args.get("page")) or 1


def _parse_agencies():
    names = request.form.getlist("agency_name")
    starts = request.form.getlist("agency_start")
    ends = request.form.getlist("agency_end")
    out = []
    for name, start, end in zip(names, starts, ends):
        name = (name or "").strip()
        if not name:
            continue
        out.append({"agency_name": name, "start_year": start, "end_year": end})
    return out


def _person_data_from_form():
    return {
        "name": request.form.get("name", ""),
        "alias": request.form.get("alias", ""),
        "kana": request.form.get("kana", ""),
        "gender": request.form.get("gender", "") or "女",
        "birth_ym": request.form.get("birth_ym", ""),
        "height": request.form.get("height", ""),
        "bust": request.form.get("bust", ""),
        "waist": request.form.get("waist", ""),
        "hip": request.form.get("hip", ""),
        "cup": request.form.get("cup", ""),
        "notes": request.form.get("notes", ""),
    }


def _work_data_from_form():
    return {
        "code": request.form.get("code", ""),
        "title": request.form.get("title", ""),
        "filename": request.form.get("filename", ""),
        "status": request.form.get("status", ""),
        "notes": request.form.get("notes", ""),
    }


def _warn_birth_ym(data):
    birth = (data.get("birth_ym") or "").strip()
    if birth and not services.check_birth_ym(birth):
        flash("出生年月格式建议为 YYYY-MM(如 1998-04),已按原文保存", "warn")


# ---------------------------------------------------------------------------
# 仪表盘
# ---------------------------------------------------------------------------
@bp.get("/")
def dashboard():
    return render_template(
        "dashboard.html",
        stats=services.dashboard_stats(g.db),
        today=services.today_heart(g.db),
        top=services.top_persons(g.db, 5),
        recent_works=services.list_works(g.db, page=1, per_page=5)[0],
    )


# ---------------------------------------------------------------------------
# 人物
# ---------------------------------------------------------------------------
@bp.get("/persons")
def persons():
    q = request.args.get("q", "").strip()
    agency = request.args.get("agency", "").strip()
    gender = request.args.get("gender", "").strip()
    sort = request.args.get("sort", "heart")
    rows, total, page, pages = services.list_persons(
        g.db, q=q, agency=agency or None, gender=gender or None,
        sort=sort, page=_page(),
    )
    return render_template(
        "persons.html", rows=rows, total=total, page=page, pages=pages,
        q=q, agency=agency, gender=gender, sort=sort, genders=GENDERS,
    )


@bp.get("/persons/new")
def person_new():
    return render_template("person_form.html", person=None, agencies=[], genders=GENDERS)


@bp.post("/persons")
def person_create():
    data = _person_data_from_form()
    if not (data["name"] or "").strip():
        flash("姓名必填", "error")
        return redirect(url_for("loverlist.person_new"))
    _warn_birth_ym(data)
    pid = services.create_person(g.db, data, _parse_agencies())
    flash(f"已添加人物:{data['name']}", "ok")
    return redirect(url_for("loverlist.person_detail", pid=pid))


@bp.get("/persons/<int:pid>")
def person_detail(pid):
    person = services.get_person(g.db, pid)
    if person is None:
        abort(404)
    return render_template(
        "person_detail.html", person=person,
        agencies=services.person_agencies(g.db, pid),
        works=services.person_works(g.db, pid),
    )


@bp.get("/persons/<int:pid>/edit")
def person_edit(pid):
    person = services.get_person(g.db, pid)
    if person is None:
        abort(404)
    return render_template(
        "person_form.html", person=person,
        agencies=services.person_agencies(g.db, pid), genders=GENDERS,
    )


@bp.post("/persons/<int:pid>")
def person_update(pid):
    if services.get_person(g.db, pid) is None:
        abort(404)
    data = _person_data_from_form()
    if not (data["name"] or "").strip():
        flash("姓名必填", "error")
        return redirect(url_for("loverlist.person_edit", pid=pid))
    _warn_birth_ym(data)
    services.update_person(g.db, pid, data, _parse_agencies())
    flash("已保存修改", "ok")
    return redirect(url_for("loverlist.person_detail", pid=pid))


@bp.post("/persons/<int:pid>/delete")
def person_delete(pid):
    services.delete_person(g.db, pid)
    flash("人物已删除", "ok")
    return redirect(url_for("loverlist.persons"))


@bp.post("/persons/<int:pid>/heart")
def person_heart(pid):
    try:
        count = services.increment_heart(g.db, pid)
    except LookupError:
        return jsonify({"error": "人物不存在"}), 404
    return jsonify({"heart_count": count})


@bp.post("/persons/<int:pid>/favorite")
def person_favorite(pid):
    try:
        state = services.toggle_favorite(g.db, pid)
    except LookupError:
        return jsonify({"error": "人物不存在"}), 404
    return jsonify({"is_favorite": state})


# ---------------------------------------------------------------------------
# 作品与阵容
# ---------------------------------------------------------------------------
@bp.get("/works")
def works():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    rows, total, page, pages = services.list_works(g.db, q=q, tag=tag or None, page=_page())
    return render_template(
        "works.html", rows=rows, total=total, page=page, pages=pages,
        q=q, tag=tag, tags=services.all_tags(g.db),
    )


@bp.get("/works/new")
def work_new():
    return render_template("work_form.html", work=None, tags_raw="")


def _save_work(wid=None):
    """创建/更新作品:成功返回作品 id,失败返回 None(消息已 flash)。"""
    data = _work_data_from_form()
    tags_raw = request.form.get("tags", "")
    code = services.normalize_code(data["code"])
    if not code:
        flash("番号必填", "error")
        return None
    if not services.check_code(code):
        flash(f"番号 {code} 不符合建议格式(如 LOV-123),已按原文保存", "warn")
    try:
        if wid is None:
            new_id = services.create_work(g.db, data, tags_raw)
            flash(f"已添加作品:{code}", "ok")
            return new_id
        services.update_work(g.db, wid, data, tags_raw)
        flash("已保存修改", "ok")
        return wid
    except sqlite3.IntegrityError:
        flash(f"番号 {code} 已存在", "error")
        return None


@bp.post("/works")
def work_create():
    new_id = _save_work()
    if new_id:
        return redirect(url_for("loverlist.work_detail", wid=new_id))
    return redirect(url_for("loverlist.work_new"))


@bp.get("/works/<int:wid>")
def work_detail(wid):
    work = services.get_work(g.db, wid)
    if work is None:
        abort(404)
    return render_template(
        "work_detail.html", work=work,
        tags=services.work_tags(g.db, wid),
        credits=services.work_credits(g.db, wid),
        persons=services.all_persons_brief(g.db),
        role_choices=services.ROLE_CHOICES,
    )


@bp.get("/works/<int:wid>/edit")
def work_edit(wid):
    work = services.get_work(g.db, wid)
    if work is None:
        abort(404)
    return render_template(
        "work_form.html", work=work,
        tags_raw=", ".join(services.work_tags(g.db, wid)),
    )


@bp.post("/works/<int:wid>")
def work_update(wid):
    if services.get_work(g.db, wid) is None:
        abort(404)
    if _save_work(wid):
        return redirect(url_for("loverlist.work_detail", wid=wid))
    return redirect(url_for("loverlist.work_edit", wid=wid))


@bp.post("/works/<int:wid>/delete")
def work_delete(wid):
    services.delete_work(g.db, wid)
    flash("作品已删除", "ok")
    return redirect(url_for("loverlist.works"))


@bp.post("/works/<int:wid>/credits")
def credit_add(wid):
    if services.get_work(g.db, wid) is None:
        abort(404)
    pid = _int_or_none(request.form.get("person_id"))
    if not pid:
        flash("请选择人物", "error")
        return redirect(url_for("loverlist.work_detail", wid=wid))
    _credit_id, err = services.add_credit(
        g.db, wid, pid,
        request.form.get("role", ""),
        request.form.get("character_name", ""),
    )
    flash(err or "阵容已添加", "error" if err else "ok")
    return redirect(url_for("loverlist.work_detail", wid=wid))


@bp.post("/credits/<int:cid>/delete")
def credit_delete(cid):
    wid = _int_or_none(request.form.get("work_id"))
    services.remove_credit(g.db, cid)
    flash("阵容已移除", "ok")
    if wid:
        return redirect(url_for("loverlist.work_detail", wid=wid))
    return redirect(url_for("loverlist.works"))


# ---------------------------------------------------------------------------
# 心动向
# ---------------------------------------------------------------------------
@bp.get("/favorites")
def favorites():
    return render_template(
        "favorites.html",
        today=services.today_heart(g.db),
        top=services.top_persons(g.db, 20),
        favs=services.favorite_persons(g.db),
    )


# ---------------------------------------------------------------------------
# 数据管理(导出/导入/演示数据)
# ---------------------------------------------------------------------------
EXPORT_KINDS = ("persons", "works", "credits")
KIND_NAMES = {"persons": "人物", "works": "作品", "credits": "阵容"}


@bp.get("/data")
def data_page():
    return render_template("data.html")


@bp.get("/export/<which>")
def export_csv(which):
    if which not in EXPORT_KINDS:
        abort(404)
    content = csvio.export_csv_string(g.db, which).encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={which}.csv"},
    )


def _decode_upload(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@bp.post("/import")
def import_csv():
    any_file = False
    for which in EXPORT_KINDS:
        fs = request.files.get(which)
        if fs is None or not fs.filename:
            continue
        any_file = True
        text = _decode_upload(fs.read())
        s = csvio.import_csv(g.db, which, io.StringIO(text))
        flash(f"{KIND_NAMES[which]}:新增 {s['created']},更新 {s['updated']},"
              f"跳过 {s['skipped']}", "ok")
    if not any_file:
        flash("请至少选择一个 CSV 文件", "error")
    return redirect(url_for("loverlist.data_page"))


@bp.post("/demo")
def seed_demo_route():
    counts = demo.seed_demo(g.db)
    if counts is None:
        flash("库中已有数据,跳过演示数据灌入(如需重来请删除 data/loverlist.db)", "warn")
    else:
        flash(f"已灌入演示数据:人物 {counts['persons']} 位、"
              f"作品 {counts['works']} 部、阵容 {counts['credits']} 条", "ok")
    return redirect(url_for("loverlist.data_page"))