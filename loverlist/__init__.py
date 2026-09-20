"""Loverlist 应用工厂。"""
from pathlib import Path

from flask import Flask, g

from .db import default_db_path, get_connection, init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(db_path=None, avatar_dir=None):
    """创建 Flask 应用。db_path 缺省为 项目根/data/loverlist.db,avatar_dir 缺省 data/avatars。"""
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config["DB_PATH"] = str(db_path) if db_path else str(default_db_path())
    app.config["AVATAR_DIR"] = str(Path(avatar_dir)) if avatar_dir else str(PROJECT_ROOT / "data" / "avatars")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 上传上限 10MB
    app.secret_key = "loverlist-local-secret"  # 本地单机使用,仅用于 flash 消息签名

    # 启动时确保库与表存在
    conn = get_connection(app.config["DB_PATH"])
    try:
        init_db(conn)
    finally:
        conn.close()

    @app.before_request
    def _open_db():
        g.db = get_connection(app.config["DB_PATH"])

    @app.teardown_appcontext
    def _close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    from .routes import bp
    app.register_blueprint(bp)
    return app
