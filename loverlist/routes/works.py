"""作品相关页面与接口:列表/详情/增删改与阵容。"""
import sqlite3

from flask import abort, flash, g, redirect, render_template, request, url_for

from .. import services
from . import bp
from .common import int_or_none, page_arg


def _work_data_from_form(code):
    return {
        "code": code,
        "title": request.form.get("title", ""),
        "is_vr": request.form.get("is_vr", ""),
        "notes": request.form.get("notes", ""),
    }


def _save_work(wid=None):
    """创建/更新作品:成功返回作品 id,失败返回 None(消息已 flash)。"""
    try:
        code = services.build_code(
            request.form.get("code_alpha", ""),
            request.form.get("code_num", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return None
    data = _work_data_from_form(code)
    tags_raw = request.form.get("tags", "")
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


@bp.get("/works")
def works():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    status = request.args.get("status", "").strip()
    rows, total, page, pages = services.list_works(
        g.db, q=q, tag=tag or None, status=status or None, page=page_arg()
    )
    return render_template(
        "works.html", rows=rows, total=total, page=page, pages=pages,
        q=q, tag=tag, status=status, statuses=services.WORK_STATUSES,
        tags=services.all_tags(g.db),
    )


@bp.get("/works/new")
def work_new():
    return render_template(
        "work_form.html", work=None, tags_raw="", code_alpha="", code_num="",
    )


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
    persons = [
        {"id": p["id"], "name": p["name"], "kana": p["kana"], "alias": p["alias"]}
        for p in services.all_persons_brief(g.db)
    ]
    return render_template(
        "work_detail.html", work=work,
        tags=services.work_tags(g.db, wid),
        credits=services.work_credits(g.db, wid),
        persons=persons,
        role_choices=services.ROLE_CHOICES,
    )


@bp.get("/works/<int:wid>/edit")
def work_edit(wid):
    work = services.get_work(g.db, wid)
    if work is None:
        abort(404)
    if "-" in work["code"]:
        code_alpha, code_num = work["code"].split("-", 1)
    else:  # 兼容历史无横线番号:整体落入英文框
        code_alpha, code_num = work["code"], ""
    return render_template(
        "work_form.html", work=work,
        tags_raw=", ".join(services.work_tags(g.db, wid)),
        code_alpha=code_alpha, code_num=code_num,
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
    pid = int_or_none(request.form.get("person_id"))
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
    wid = int_or_none(request.form.get("work_id"))
    services.remove_credit(g.db, cid)
    flash("阵容已移除", "ok")
    if wid:
        return redirect(url_for("loverlist.work_detail", wid=wid))
    return redirect(url_for("loverlist.works"))