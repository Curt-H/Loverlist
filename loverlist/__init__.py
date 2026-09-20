"""Loverlist 应用工厂。

数据位置解析:
- create_app(db_path, avatar_dir) 显式指定(来自 data.ini / --data-dir / 设置页);
- setup_error 非 None 表示数据位置不可用:应用进入引导模式,全部页面重定向到 /setup,
  此时不会读写任何数据库,直到在引导页完成配置。
"""
from pathlib import Path

from flask import Flask, g, redirect, request, url_for

from . import services
from .db import default_db_path, get_connection, init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_SETUP_ENDPOINTS = ("loverlist.setup_page", "loverlist.setup_save")


def create_app(db_path=None, avatar_dir=None, setup_error: str | None = None):
    """创建 Flask 应用。db_path 缺省为 项目根/data/loverlist.db,avatar_dir 缺省 data/avatars。"""
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config["DB_PATH"] = str(db_path) if db_path else str(default_db_path())
    app.config["AVATAR_DIR"] = str(Path(avatar_dir)) if avatar_dir else str(PROJECT_ROOT / "data" / "avatars")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 上传上限 10MB
    app.config["SETUP_ERROR"] = setup_error
    app.secret_key = "loverlist-local-secret"  # 本地单机使用,仅用于 flash 消息签名

    # 正常模式:启动时确保库与表存在;引导模式:不碰任何数据库
    if not setup_error:
        conn = get_connection(app.config["DB_PATH"])
        try:
            init_db(conn)
        finally:
            conn.close()

    @app.before_request
    def _guard_and_open_db():
        if app.config.get("SETUP_ERROR"):
            # 引导模式:除设置页与静态资源外全部重定向,且不打开任何数据库连接
            if request.endpoint not in _SETUP_ENDPOINTS and request.endpoint != "static":
                return redirect(url_for("loverlist.setup_page"))
            return None
        g.db = get_connection(app.config["DB_PATH"])

    @app.teardown_appcontext
    def _close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    app.jinja_env.filters["age"] = services.age_from_birth_ym

    @app.context_processor
    def _inject_review_count():
        if app.config.get("SETUP_ERROR"):
            return {"review_count": 0}
        return {"review_count": services.pending_review_count(g.db)}

    from .routes import bp
    app.register_blueprint(bp)
    return app
