"""数据管理:CSV 导出/导入与演示数据。"""
import io

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

from .. import csvio, demo, services
from . import bp

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