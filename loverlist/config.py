"""数据位置配置:项目根 data.ini 记录数据文件夹(可指向本地盘或网络盘/UNC)。"""
import configparser
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "data.ini"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def load_data_dir() -> str | None:
    """读取配置的数据文件夹;未配置返回 None(此时使用本地 data/)。"""
    if not CONFIG_PATH.exists():
        return None
    cp = configparser.ConfigParser()
    cp.read(CONFIG_PATH, encoding="utf-8")
    if cp.has_option("data", "dir"):
        value = cp.get("data", "dir").strip()
        return value or None
    return None


def save_data_dir(path: str) -> None:
    """把数据文件夹路径写入 data.ini。"""
    cp = configparser.ConfigParser()
    cp["data"] = {"dir": str(path)}
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        cp.write(f)


def check_dir(path: str) -> str | None:
    """校验数据文件夹可创建/可读写;返回错误信息,None 表示可用。"""
    try:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".loverlist_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return None
    except OSError as exc:
        return f"无法访问该位置({exc})"


def local_data_ready() -> bool:
    """本地默认位置是否已有数据(库文件或头像)。"""
    return (DEFAULT_DATA_DIR / "loverlist.db").exists() or (DEFAULT_DATA_DIR / "avatars").exists()


def copy_local_data(dest: str, src_dir: Path | None = None) -> tuple[bool, int]:
    """把本地数据(loverlist.db 与 avatars/)复制到 dest;返回 (是否复制了库, 头像文件数)。"""
    src = Path(src_dir) if src_dir else DEFAULT_DATA_DIR
    dst = Path(dest)
    dst.mkdir(parents=True, exist_ok=True)
    db_copied = False
    src_db = src / "loverlist.db"
    if src_db.exists():
        shutil.copy2(src_db, dst / "loverlist.db")
        db_copied = True
    avatar_count = 0
    src_avatars = src / "avatars"
    if src_avatars.exists():
        dst_avatars = dst / "avatars"
        dst_avatars.mkdir(parents=True, exist_ok=True)
        for f in src_avatars.iterdir():
            if f.is_file():
                shutil.copy2(f, dst_avatars / f.name)
                avatar_count += 1
    return db_copied, avatar_count