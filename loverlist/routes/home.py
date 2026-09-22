"""仪表盘。"""
from flask import g, render_template

from .. import services
from . import bp


@bp.get("/")
def dashboard():
    return render_template(
        "dashboard.html",
        stats=services.dashboard_stats(g.db),
        today=services.today_heart(g.db),
        top=services.top_persons(g.db, 5),
        recent_works=services.list_works(g.db, exclude_rejected=True, page=1, per_page=5)[0],
        today_review=services.today_review(g.db),
    )