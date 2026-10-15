"""评审页与作品状态判定:状态的更改入口(评审页 + 首页今日评审快捷判定)。"""
from flask import abort, flash, g, redirect, render_template, request, url_for

from .. import services
from . import bp


@bp.get("/review")
def review_page():
    return render_template(
        "review.html",
        pending=services.review_list(g.db),
        judged=services.judged_works(g.db),
    )


@bp.post("/works/<int:wid>/status")
def work_set_status(wid):
    """更改作品状态(评审页与首页「今日评审」快捷按钮均调用);非法状态抛 ValueError。

    可选 next 表单字段指定判定后的跳回页面(仅接受站内相对路径,默认回评审页)。
    """
    work = services.get_work(g.db, wid)
    if work is None:
        abort(404)
    status = request.form.get("status", "")
    try:
        services.set_work_status(g.db, wid, status)
    except ValueError:
        flash("未知的状态值", "error")
    else:
        flash(f"《{work['code']}》状态已更新为:{status}", "ok")
    next_url = request.form.get("next", "")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("loverlist.review_page")  # 非站内地址一律回退,防开放重定向
    return redirect(next_url)