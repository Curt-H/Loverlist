"""人物相关页面与接口:列表/详情/增删改、心动与收藏、头像。"""
import time
from pathlib import Path

from flask import (abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)

from .. import services
from . import bp
from .common import page_arg

GENDERS = ["女", "男", "其他"]


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


def _warn_birth_ym(data):
    birth = (data.get("birth_ym") or "").strip()
    if birth and not services.check_birth_ym(birth):
        flash("出生年月格式建议为 YYYY-MM(如 1998-04),已按原文保存", "warn")


@bp.get("/persons")
def persons():
    q = request.args.get("q", "").strip()
    agency = request.args.get("agency", "").strip()
    gender = request.args.get("gender", "").strip()
    sort = request.args.get("sort", "heart")
    dir_ = request.args.get("dir", "").strip().lower()
    if dir_ not in ("asc", "desc"):
        dir_ = services.SORT_DEFAULT_DIR.get(sort, "DESC").lower()
    rows, total, page, pages = services.list_persons(
        g.db, q=q, agency=agency or None, gender=gender or None,
        sort=sort, dir=dir_, page=page_arg(),
    )
    return render_template(
        "persons.html", rows=rows, total=total, page=page, pages=pages,
        q=q, agency=agency, gender=gender, sort=sort, dir=dir_, genders=GENDERS,
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
    _remove_avatar_files(pid)
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
# 头像(1:1,512×512,本地存储于 data/avatars)
# ---------------------------------------------------------------------------
AVATAR_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"))


def _avatar_dir() -> Path:
    return Path(current_app.config["AVATAR_DIR"])


def _remove_avatar_files(pid: int) -> None:
    d = _avatar_dir()
    if d.exists():
        for f in d.glob(f"{pid}_*.*"):
            f.unlink(missing_ok=True)


@bp.post("/persons/<int:pid>/avatar")
def avatar_upload(pid):
    """接收前端裁剪/缩放好的 512×512 图片并落盘。"""
    if services.get_person(g.db, pid) is None:
        abort(404)
    detail = url_for("loverlist.person_detail", pid=pid)
    fs = request.files.get("file")
    if fs is None or not fs.filename:
        flash("请选择图片文件", "error")
        return redirect(detail)
    raw = fs.read()
    ext = next((e for magic, e in AVATAR_MAGIC if raw.startswith(magic)), None)
    if ext == "webp" and raw[8:12] != b"WEBP":
        ext = None
    if ext is None:
        flash("不支持的图片格式(请使用 PNG / JPEG / WebP)", "error")
        return redirect(detail)
    _remove_avatar_files(pid)  # 换头像时清掉旧文件
    filename = f"{pid}_{int(time.time())}.{ext}"
    d = _avatar_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_bytes(raw)
    g.db.execute("UPDATE persons SET avatar = ? WHERE id = ?", (filename, pid))
    g.db.commit()
    flash("头像已更新", "ok")
    return redirect(detail)


@bp.get("/avatars/<filename>")
def avatar_file(filename):
    return send_from_directory(_avatar_dir(), filename)


@bp.post("/persons/<int:pid>/avatar/delete")
def avatar_delete(pid):
    if services.get_person(g.db, pid) is None:
        abort(404)
    _remove_avatar_files(pid)
    g.db.execute("UPDATE persons SET avatar = '' WHERE id = ?", (pid,))
    g.db.commit()
    flash("头像已移除", "ok")
    return redirect(url_for("loverlist.person_detail", pid=pid))