"""路由层共用小工具。"""
from flask import request


def int_or_none(value):
    """宽松转整数:空/非法返回 None。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def page_arg():
    """读取分页参数 page(缺省 1)。与视图内局部变量 page 区分,故意不叫 page。"""
    return int_or_none(request.args.get("page")) or 1