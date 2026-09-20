"""虚构演示数据(仅空库时灌入)。"""
import sqlite3

_DEMO_PERSONS = [
    # (姓名, 别名, 假名, 性别, 出生年月, 身高, B, W, H, 罩杯, 事务所史[(名, 起, 止)])
    ("佐藤ひなた", "ひなた", "さとうひなた", "女", "1998-04", 158, 86, 58, 85, "F",
     [("プラチナプロダクション", 2016, 2018), ("スターライン", 2018, None)]),
    ("鈴木愛理", "ありん", "すずきあいり", "女", "2000-11", 162, 90, 60, 92, "G",
     [("スターライン", 2019, None)]),
    ("高橋結衣", "ゆいぴょん", "たかはしゆい", "女", "1999-07", 155, 83, 57, 82, "E",
     [("月光ミュージック", 2017, 2020), ("プラチナプロダクション", 2020, None)]),
    ("渡辺美月", "みっきー", "わたなべみつき", "女", "2001-02", 168, 92, 62, 94, "H",
     [("スターライン", 2021, None)]),
    ("山本汐音", "しおん", "やまもとしおね", "女", "1997-09", 160, 88, 59, 88, "F",
     [("月光ミュージック", 2015, 2019)]),
    ("中村梨々花", "りりか", "なかむらりりか", "女", "2002-05", 154, 82, 56, 80, "D",
     [("ネクストドア", 2022, None)]),
    ("小林千夏", "ちなつ", "こばやしちなつ", "女", "1996-12", 165, 89, 61, 90, "G",
     [("プラチナプロダクション", 2014, 2018)]),
    ("一条真澄", "", "いちじょうますみ", "男", "1975-03", None, None, None, None, "",
     [("オオトリフィルム", 2010, None)]),
]

_DEMO_WORKS = [
    # (番号, 标题, [标签])
    ("LOV-001", "初夏の恋人", ["恋爱", "青春"]),
    ("LOV-002", "真夏の夜の夢", ["恋爱", "剧情"]),
    ("LOV-003", "放課後ダイアリー", ["校园", "青春"]),
    ("LOV-004", "星降る夜に", ["剧情", "治愈"]),
    ("LOV-005", "ドキドキ★サマー", ["综艺", "喜剧"]),
    ("LOV-006", "冬のひみつ", ["恋爱", "治愈"]),
    ("LOV-007", "都市伝説", ["悬疑", "剧情"]),
    ("LOV-008", "春をさがして", ["青春", "治愈"]),
    ("LOV-009", "月光パラダイス", ["喜剧"]),
    ("LOV-010", "最終回の向こう", ["剧情"]),
]

# 出演分配:番号 -> [(人物名, 角色名)]
_CAST = {
    "LOV-001": [("佐藤ひなた", "ヒロイン・みなみ"), ("鈴木愛理", "親友・あかり")],
    "LOV-002": [("高橋結衣", "ユイ"), ("渡辺美月", "ミツキ")],
    "LOV-003": [("中村梨々花", "りりか"), ("佐藤ひなた", "先輩")],
    "LOV-004": [("山本汐音", "汐音"), ("小林千夏", "母")],
    "LOV-005": [("渡辺美月", "レギュラー"), ("鈴木愛理", "ゲスト")],
    "LOV-006": [("小林千夏", "千夏"), ("高橋結衣", "妹")],
    "LOV-007": [("山本汐音", "記者"), ("渡辺美月", "謎の女")],
    "LOV-008": [("中村梨々花", "主人公"), ("佐藤ひなた", "カメオ出演")],
    "LOV-009": [("鈴木愛理", "主演")],
    "LOV-010": [("小林千夏", "主演"), ("高橋結衣", "ヒロイン")],
}


def seed_demo(conn: sqlite3.Connection):
    """向空库灌入演示数据;库非空时返回 None。成功返回数量字典。"""
    from . import services

    if conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0] > 0:
        return None
    if conn.execute("SELECT COUNT(*) FROM works").fetchone()[0] > 0:
        return None

    name_to_id = {}
    for (name, alias, kana, gender, birth, h, b, w, hip, cup, agencies) in _DEMO_PERSONS:
        pid = services.create_person(
            conn,
            {"name": name, "alias": alias, "kana": kana, "gender": gender,
             "birth_ym": birth, "height": h, "bust": b, "waist": w, "hip": hip,
             "cup": cup, "notes": ""},
            [{"agency_name": n, "start_year": s, "end_year": e} for (n, s, e) in agencies],
        )
        name_to_id[name] = pid

    code_to_id = {}
    for (code, title, tags) in _DEMO_WORKS:
        wid = services.create_work(conn, {"code": code, "title": title}, ",".join(tags))
        code_to_id[code] = wid

    n_credits = 0
    director = name_to_id["一条真澄"]
    for code, cast in _CAST.items():
        for person_name, role_name in cast:
            services.add_credit(conn, code_to_id[code], name_to_id[person_name],
                                "出演", role_name)
            n_credits += 1
        services.add_credit(conn, code_to_id[code], director, "导演", "")
        n_credits += 1

    # 给前三位一点心动值,让今日心动/榜单立刻有味道
    for name, hearts in [("佐藤ひなた", 3), ("鈴木愛理", 7), ("渡辺美月", 12)]:
        for _ in range(hearts):
            services.increment_heart(conn, name_to_id[name])
    services.toggle_favorite(conn, name_to_id["渡辺美月"])

    return {"persons": len(_DEMO_PERSONS), "works": len(_DEMO_WORKS), "credits": n_credits}