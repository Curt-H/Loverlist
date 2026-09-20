"""Web 路由包:按页面域拆分模块,所有视图注册在同一个 Blueprint 上。"""
from flask import Blueprint

bp = Blueprint("loverlist", __name__)

from . import data, home, persons, review, setup, works  # noqa: E402,F401 (导入即注册视图)