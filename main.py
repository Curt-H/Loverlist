"""Loverlist 入口:python main.py [--demo] [--host H] [--port P] [--no-browser]"""
import argparse
import threading
import webbrowser

from loverlist import create_app
from loverlist.db import get_connection, init_db
from loverlist.demo import seed_demo


def main():
    parser = argparse.ArgumentParser(description="Loverlist —— 人物与影视作品管理系统")
    parser.add_argument("--demo", action="store_true",
                        help="灌入虚构演示数据后退出(空库时生效)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址,默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=5000, help="监听端口,默认 5000")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    app = create_app()  # 同时完成建库

    if args.demo:
        conn = get_connection()
        try:
            counts = seed_demo(conn)
        finally:
            conn.close()
        if counts is None:
            print("库中已有数据,跳过演示数据灌入(如需重来请删除 data/loverlist.db)")
        else:
            print(f"演示数据已灌入:人物 {counts['persons']} 位,"
                  f"作品 {counts['works']} 部,阵容 {counts['credits']} 条")
        return

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"💗 Loverlist 运行中:{url}(Ctrl+C 退出)")
    from waitress import serve
    serve(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()