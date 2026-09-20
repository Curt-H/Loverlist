"""评审页:作品状态的唯一更改入口。"""
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
    return redirect(url_for("loverlist.review_page"))