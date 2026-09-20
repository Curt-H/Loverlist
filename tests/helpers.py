"""测试共用工具。"""


def make_conn(testcase):
    """给测试类挂一个已建库的内存连接。"""
    from loverlist import db
    testcase.conn = db.get_connection(":memory:")
    db.init_db(testcase.conn)
    testcase.addCleanup(testcase.conn.close)


def person_data(**over):
    data = {
        "name": "佐藤ひなた", "alias": "ひなた", "kana": "さとうひなた",
        "gender": "女", "birth_ym": "1998-04", "height": "158",
        "bust": "86", "waist": "58", "hip": "85", "cup": "F", "notes": "",
    }
    data.update(over)
    return data