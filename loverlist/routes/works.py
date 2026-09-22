"""作品相关页面与接口:列表/详情/增删改与阵容。"""
import sqlite3

from flask import (abort, flash, g, jsonify, redirect, render_template, request,
                   url_for)

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


def _work_form_context(wid=None):
    """校验/查重失败原地重渲表单时的回填上下文(从当前请求恢复已填内容)。"""
    code_alpha = request.form.get("code_alpha", "")
    code_num = request.form.get("code_num", "")
    try:
        code = services.build_code(code_alpha, code_num)
    except ValueError:
        code = ""
    return {
        "work": {
            "id": wid, "code": code,
            "title": request.form.get("title", ""),
            "is_vr": request.form.get("is_vr", ""),
            "notes": request.form.get("notes", ""),
        },
        "tags_raw": request.form.get("tags", ""),
        "code_alpha": code_alpha, "code_num": code_num,
    }


def _save_work(wid=None):
    """创建/更新作品:成功返回 (id, ""),失败返回 (None, 错误消息)(消息已 flash)。"""
    try:
        code = services.build_code(
            request.form.get("code_alpha", ""),
            request.form.get("code_num", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return None, str(exc)
    data = _work_data_from_form(code)
    tags_raw = request.form.get("tags", "")
    try:
        if wid is None:
            new_id = services.create_work(g.db, data, tags_raw)
            flash(f"已添加作品:{code}", "ok")
            return new_id, ""
        services.update_work(g.db, wid, data, tags_raw)
        flash("已保存修改", "ok")
        return wid, ""
    except ValueError as exc:  # 服务层查重:番号已存在
        flash(str(exc), "error")
        return None, str(exc)
    except sqlite3.IntegrityError:  # DB 唯一约束兜底
        msg = f"番号 {code} 已存在"
        flash(msg, "error")
        return None, msg


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


@bp.get("/works/dup-check")
def work_dup_check():
    """输入时自动查重:番号两段归一拼接后精确匹配;exclude_id 用于编辑态排除自身。
    段不完整/非法时返回 duplicate=false(不提示、不报错,由提交时校验兜底)。"""
    try:
        code = services.build_code(request.args.get("alpha", ""), request.args.get("num", ""))
    except ValueError:
        return jsonify({"duplicate": False, "url": None, "label": ""})
    exclude = int_or_none(request.args.get("exclude_id"))
    dup = services.find_work_by_code(g.db, code, exclude_id=exclude)
    if dup is None:
        return jsonify({"duplicate": False, "url": None, "label": ""})
    return jsonify({
        "duplicate": True,
        "url": url_for("loverlist.work_detail", wid=dup["id"]),
        "label": f"番号 {code} 已存在",
    })


@bp.post("/works")
def work_create():
    new_id, _err = _save_work()
    if new_id:
        return redirect(url_for("loverlist.work_detail", wid=new_id))
    return render_template("work_form.html", **_work_form_context())


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
    new_id, _err = _save_work(wid)
    if new_id:
        return redirect(url_for("loverlist.work_detail", wid=new_id))
    return render_template("work_form.html", **_work_form_context(wid))


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