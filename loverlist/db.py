"""Loverlist 数据层:SQLite 连接与建库。"""
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "loverlist.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,              -- 姓名(必填)
    alias       TEXT    NOT NULL DEFAULT '',   -- 别名
    kana        TEXT    NOT NULL DEFAULT '',   -- 假名(日文)
    gender      TEXT    NOT NULL DEFAULT '女', -- 性别(默认女)
    birth_ym    TEXT    NOT NULL DEFAULT '',   -- 出生年月 YYYY-MM
    height      INTEGER,                       -- 身高 cm
    bust        INTEGER,                       -- 胸围 B
    waist       INTEGER,                       -- 腰围 W
    hip         INTEGER,                       -- 臀围 H
    cup         TEXT    NOT NULL DEFAULT '',   -- 罩杯
    avatar      TEXT    NOT NULL DEFAULT '',   -- 头像文件名(512×512,存 data/avatars)
    heart_count INTEGER NOT NULL DEFAULT 0,    -- 心动指数(无上限,点击+1)
    is_favorite INTEGER NOT NULL DEFAULT 0,    -- 收藏/心头好
    notes       TEXT    NOT NULL DEFAULT '',   -- 备注
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS agency_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    agency_name TEXT    NOT NULL,              -- 事务所名
    start_year  INTEGER,                       -- 起始年
    end_year    INTEGER                        -- 结束年,NULL = 至今
);

CREATE TABLE IF NOT EXISTS works (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT    NOT NULL UNIQUE,        -- 番号(必填唯一,大写归一)
    title      TEXT    NOT NULL DEFAULT '',    -- 标题
    filename   TEXT    NOT NULL DEFAULT '',    -- 文件名(预留字段)
    status     TEXT    NOT NULL DEFAULT '评审中', -- 状态:评审中/已收录/不予收录
    notes      TEXT    NOT NULL DEFAULT '',    -- 备注
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS work_tags (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    tag     TEXT    NOT NULL,                    -- 风格TAG
    UNIQUE(work_id, tag)
);

CREATE TABLE IF NOT EXISTS credits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id      INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    work_id        INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    role           TEXT    NOT NULL DEFAULT '出演', -- 关系类型
    character_name TEXT    NOT NULL DEFAULT '',     -- 饰演角色名(可空)
    UNIQUE(person_id, work_id, role)
);

CREATE INDEX IF NOT EXISTS idx_persons_heart   ON persons(heart_count DESC);
CREATE INDEX IF NOT EXISTS idx_agency_person   ON agency_history(person_id);
CREATE INDEX IF NOT EXISTS idx_tags_work       ON work_tags(work_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag        ON work_tags(tag);
CREATE INDEX IF NOT EXISTS idx_credits_person  ON credits(person_id);
CREATE INDEX IF NOT EXISTS idx_credits_work    ON credits(work_id);
"""


def default_db_path() -> Path:
    """默认数据库文件路径:项目根/data/loverlist.db"""
    return DEFAULT_DB_PATH


def get_connection(db_path=None) -> sqlite3.Connection:
    """打开连接(行以 dict 风格访问,开启外键级联);路径不存在时自动建目录。"""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """建表(幂等);老库自动补新增列(轻量迁移)与状态值归一。"""
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(persons)")}
    if "avatar" not in cols:
        conn.execute("ALTER TABLE persons ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")
    # 历史数据迁移:老库空状态视为已收录(新作品由服务层默认写入「评审中」,不受影响)
    conn.execute("UPDATE works SET status = '已收录' WHERE status = ''")
    conn.commit()