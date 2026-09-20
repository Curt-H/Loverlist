"""Loverlist 测试入口:python run_tests.py [-v] [PATTERN]

为什么不用 `-m unittest discover tests`:内嵌版 Python(python311._pth 的
隔离模式)不会把项目根加入模块搜索路径,unittest 无法导入 loverlist/tests。
本入口与 main.py 一样自带路径修复,任意解释器、任意工作目录下均可运行。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    pattern = args[0] if args else "test*.py"
    verbosity = 2 if "-v" in sys.argv else 1
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
