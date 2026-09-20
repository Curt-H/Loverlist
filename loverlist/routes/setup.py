"""数据位置引导页:找不到数据文件夹时的兜底入口,也可随时主动调整。"""
from pathlib import Path

from flask import current_app, flash, redirect, render_template, request, url_for

from .. import config
from ..db import get_connection, init_db
from . import bp


@bp.get("/setup")
def setup_page():
    using_local = (Path(current_app.config["DB_PATH"])
                   == config.DEFAULT_DATA_DIR / "loverlist.db")
    return render_template(
        "setup.html",
        setup_error=current_app.config.get("SETUP_ERROR"),
        current_dir=config.load_data_dir() or "",
        copy_available=config.local_data_ready() and using_local,
    )


@bp.post("/setup")
def setup_save():
    path = request.form.get("data_dir", "").strip()
    if not path:
        flash("请填写数据文件夹位置", "error")
        return redirect(url_for("loverlist.setup_page"))
    err = config.check_dir(path)
    if err:
        flash(err, "error")
        return redirect(url_for("loverlist.setup_page"))
    if request.form.get("copy_local") == "1":
        try:
            db_copied, avatar_count = config.copy_local_data(path)
        except OSError as exc:
            flash(f"复制本地数据失败:{exc}(配置未更改)", "error")
            return redirect(url_for("loverlist.setup_page"))
        flash(f"已复制本地数据:数据库{'✓' if db_copied else '无'},头像 {avatar_count} 个", "ok")
    config.save_data_dir(path)
    # 热切换当前进程到新数据位置(建库建表,无需重启)
    db_path = Path(path) / "loverlist.db"
    avatar_dir = Path(path) / "avatars"
    conn = get_connection(db_path)
    try:
        init_db(conn)
    finally:
        conn.close()
    current_app.config["DB_PATH"] = str(db_path)
    current_app.config["AVATAR_DIR"] = str(avatar_dir)
    current_app.config["SETUP_ERROR"] = None
    flash(f"数据位置已设置为:{path}", "ok")
    return redirect(url_for("loverlist.dashboard"))