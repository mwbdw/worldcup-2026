
#!/usr/bin/env python3
"""2026美加墨世界杯比分预测网站"""

import os
import time
import threading
from functools import wraps
from flask import Flask, request, session, jsonify, send_from_directory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
import requests as http

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'worldcup.db')
PORT     = int(os.environ.get('PORT', 3000))

# ── 数据库连接（本地 SQLite / 云端 PostgreSQL 自动切换）──────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')
if DATABASE_URL.startswith('postgres://'):          # Render 旧格式兼容
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

IS_SQLITE = DATABASE_URL.startswith('sqlite')

if IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ── DB 工具函数 ────────────────────────────────────────────────────────────
def fetch_all(sql, params=None):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params or {}).mappings()]

def fetch_one(sql, params=None):
    with engine.connect() as c:
        r = c.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

def run(sql, params=None):
    with engine.begin() as c:
        c.execute(text(sql), params or {})

def run_many(sql, param_list):
    with engine.begin() as c:
        c.execute(text(sql), param_list)

# ── Schema ─────────────────────────────────────────────────────────────────
SQLITE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        password     TEXT NOT NULL,
        is_admin     INTEGER DEFAULT 0,
        total_points INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS matches (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        match_date  TEXT NOT NULL,
        match_time  TEXT NOT NULL,
        home_team   TEXT NOT NULL,
        away_team   TEXT NOT NULL,
        group_name  TEXT DEFAULT '',
        home_score  INTEGER,
        away_score  INTEGER,
        settled     INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS predictions (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id   INTEGER NOT NULL,
        match_id  INTEGER NOT NULL,
        pred_home INTEGER NOT NULL,
        pred_away INTEGER NOT NULL,
        points    INTEGER,
        UNIQUE(user_id, match_id),
        FOREIGN KEY(user_id)  REFERENCES users(id),
        FOREIGN KEY(match_id) REFERENCES matches(id)
    )""",
]

PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id           SERIAL PRIMARY KEY,
        username     TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        password     TEXT NOT NULL,
        is_admin     INTEGER DEFAULT 0,
        total_points INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS matches (
        id          SERIAL PRIMARY KEY,
        match_date  TEXT NOT NULL,
        match_time  TEXT NOT NULL,
        home_team   TEXT NOT NULL,
        away_team   TEXT NOT NULL,
        group_name  TEXT DEFAULT '',
        home_score  INTEGER,
        away_score  INTEGER,
        settled     INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS predictions (
        id        SERIAL PRIMARY KEY,
        user_id   INTEGER NOT NULL,
        match_id  INTEGER NOT NULL,
        pred_home INTEGER NOT NULL,
        pred_away INTEGER NOT NULL,
        points    INTEGER,
        UNIQUE(user_id, match_id),
        FOREIGN KEY(user_id)  REFERENCES users(id),
        FOREIGN KEY(match_id) REFERENCES matches(id)
    )""",
]

# ── 种子数据 ───────────────────────────────────────────────────────────────
USERS_SEED = [
    {'username':'admin',   'display_name':'管理员',   'password':'admin888', 'is_admin':1},
    {'username':'player1', 'display_name':'茅', 'password':'1234', 'is_admin':0},
    {'username':'player2', 'display_name':'闫', 'password':'1234', 'is_admin':0},
    {'username':'player3', 'display_name':'王', 'password':'1234', 'is_admin':0},
    {'username':'player4', 'display_name':'岳', 'password':'1234', 'is_admin':0},
]

MATCHES_SEED = [
    # 所有时间均为北京时间（UTC+8）
    # ── 第1比赛日 6月12日 ──────────────────────────────────────
    {'match_date':'2026-06-12','match_time':'03:00','home_team':'🇲🇽 墨西哥',       'away_team':'🇿🇦 南非',          'group_name':'A组'},
    {'match_date':'2026-06-12','match_time':'10:00','home_team':'🇰🇷 韩国',         'away_team':'🇨🇿 捷克',          'group_name':'A组'},
    # ── 第2比赛日 6月13日 ──────────────────────────────────────
    {'match_date':'2026-06-13','match_time':'03:00','home_team':'🇨🇦 加拿大',       'away_team':'🇧🇦 波黑',          'group_name':'B组'},
    {'match_date':'2026-06-13','match_time':'09:00','home_team':'🇺🇸 美国',         'away_team':'🇵🇾 巴拉圭',        'group_name':'D组'},
    # ── 第3比赛日 6月14日 ──────────────────────────────────────
    {'match_date':'2026-06-14','match_time':'03:00','home_team':'🇶🇦 卡塔尔',       'away_team':'🇨🇭 瑞士',          'group_name':'B组'},
    {'match_date':'2026-06-14','match_time':'06:00','home_team':'🇧🇷 巴西',         'away_team':'🇲🇦 摩洛哥',        'group_name':'C组'},
    {'match_date':'2026-06-14','match_time':'09:00','home_team':'🏴󠁧󠁢󠁳󠁣󠁴󠁿 苏格兰',       'away_team':'🇭🇹 海地',          'group_name':'C组'},
    {'match_date':'2026-06-14','match_time':'12:00','home_team':'🇦🇺 澳大利亚',     'away_team':'🇹🇷 土耳其',        'group_name':'D组'},
    # ── 第4比赛日 6月15日 ──────────────────────────────────────
    {'match_date':'2026-06-15','match_time':'01:00','home_team':'🇩🇪 德国',         'away_team':'🇨🇼 库拉索',        'group_name':'E组'},
    {'match_date':'2026-06-15','match_time':'04:00','home_team':'🇳🇱 荷兰',         'away_team':'🇯🇵 日本',          'group_name':'F组'},
    {'match_date':'2026-06-15','match_time':'07:00','home_team':'🇨🇮 科特迪瓦',     'away_team':'🇪🇨 厄瓜多尔',      'group_name':'E组'},
    {'match_date':'2026-06-15','match_time':'10:00','home_team':'🇸🇪 瑞典',         'away_team':'🇹🇳 突尼斯',        'group_name':'F组'},
    # ── 第5比赛日 6月16日 ──────────────────────────────────────
    {'match_date':'2026-06-16','match_time':'00:00','home_team':'🇪🇸 西班牙',       'away_team':'🇨🇻 佛得角',        'group_name':'H组'},
    {'match_date':'2026-06-16','match_time':'03:00','home_team':'🇧🇪 比利时',       'away_team':'🇪🇬 埃及',          'group_name':'G组'},
    {'match_date':'2026-06-16','match_time':'06:00','home_team':'🇸🇦 沙特阿拉伯',   'away_team':'🇺🇾 乌拉圭',        'group_name':'H组'},
    {'match_date':'2026-06-16','match_time':'09:00','home_team':'🇮🇷 伊朗',         'away_team':'🇳🇿 新西兰',        'group_name':'G组'},
    # ── 第6比赛日 6月17日 ──────────────────────────────────────
    {'match_date':'2026-06-17','match_time':'03:00','home_team':'🇫🇷 法国',         'away_team':'🇸🇳 塞内加尔',      'group_name':'I组'},
    {'match_date':'2026-06-17','match_time':'06:00','home_team':'🇮🇶 伊拉克',       'away_team':'🇳🇴 挪威',          'group_name':'I组'},
    {'match_date':'2026-06-17','match_time':'09:00','home_team':'🇦🇷 阿根廷',       'away_team':'🇩🇿 阿尔及利亚',    'group_name':'J组'},
    {'match_date':'2026-06-17','match_time':'12:00','home_team':'🇦🇹 奥地利',       'away_team':'🇯🇴 约旦',          'group_name':'J组'},
    # ── 第7比赛日 6月18日 ──────────────────────────────────────
    {'match_date':'2026-06-18','match_time':'01:00','home_team':'🇵🇹 葡萄牙',       'away_team':'🇨🇩 刚果（金）',    'group_name':'K组'},
    {'match_date':'2026-06-18','match_time':'04:00','home_team':'🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格兰',       'away_team':'🇭🇷 克罗地亚',      'group_name':'L组'},
    {'match_date':'2026-06-18','match_time':'07:00','home_team':'🇬🇭 加纳',         'away_team':'🇵🇦 巴拿马',        'group_name':'L组'},
    {'match_date':'2026-06-18','match_time':'10:00','home_team':'🇺🇿 乌兹别克斯坦', 'away_team':'🇨🇴 哥伦比亚',      'group_name':'K组'},
    # ── 第8比赛日 6月19日 ──────────────────────────────────────
    {'match_date':'2026-06-19','match_time':'00:00','home_team':'🇨🇿 捷克',         'away_team':'🇿🇦 南非',          'group_name':'A组'},
    {'match_date':'2026-06-19','match_time':'03:00','home_team':'🇨🇭 瑞士',         'away_team':'🇧🇦 波黑',          'group_name':'B组'},
    {'match_date':'2026-06-19','match_time':'06:00','home_team':'🇨🇦 加拿大',       'away_team':'🇶🇦 卡塔尔',        'group_name':'B组'},
    {'match_date':'2026-06-19','match_time':'09:00','home_team':'🇲🇽 墨西哥',       'away_team':'🇰🇷 韩国',          'group_name':'A组'},
    # ── 第9比赛日 6月20日 ──────────────────────────────────────
    {'match_date':'2026-06-20','match_time':'03:00','home_team':'🇺🇸 美国',         'away_team':'🇦🇺 澳大利亚',      'group_name':'D组'},
    {'match_date':'2026-06-20','match_time':'06:00','home_team':'🏴󠁧󠁢󠁳󠁣󠁴󠁿 苏格兰',       'away_team':'🇲🇦 摩洛哥',        'group_name':'C组'},
    {'match_date':'2026-06-20','match_time':'08:30','home_team':'🇧🇷 巴西',         'away_team':'🇭🇹 海地',          'group_name':'C组'},
    {'match_date':'2026-06-20','match_time':'11:00','home_team':'🇹🇷 土耳其',       'away_team':'🇵🇾 巴拉圭',        'group_name':'D组'},
    # ── 第10比赛日 6月21日 ─────────────────────────────────────
    {'match_date':'2026-06-21','match_time':'01:00','home_team':'🇳🇱 荷兰',         'away_team':'🇸🇪 瑞典',          'group_name':'F组'},
    {'match_date':'2026-06-21','match_time':'04:00','home_team':'🇩🇪 德国',         'away_team':'🇨🇮 科特迪瓦',      'group_name':'E组'},
    {'match_date':'2026-06-21','match_time':'11:00','home_team':'🇪🇨 厄瓜多尔',     'away_team':'🇨🇼 库拉索',        'group_name':'E组'},
    {'match_date':'2026-06-21','match_time':'12:00','home_team':'🇹🇳 突尼斯',       'away_team':'🇯🇵 日本',          'group_name':'F组'},
    # ── 第11比赛日 6月22日 ─────────────────────────────────────
    {'match_date':'2026-06-22','match_time':'00:00','home_team':'🇪🇸 西班牙',       'away_team':'🇸🇦 沙特阿拉伯',    'group_name':'H组'},
    {'match_date':'2026-06-22','match_time':'03:00','home_team':'🇧🇪 比利时',       'away_team':'🇮🇷 伊朗',          'group_name':'G组'},
    {'match_date':'2026-06-22','match_time':'06:00','home_team':'🇺🇾 乌拉圭',       'away_team':'🇨🇻 佛得角',        'group_name':'H组'},
    {'match_date':'2026-06-22','match_time':'09:00','home_team':'🇳🇿 新西兰',       'away_team':'🇪🇬 埃及',          'group_name':'G组'},
    # ── 第12比赛日 6月23日 ─────────────────────────────────────
    {'match_date':'2026-06-23','match_time':'01:00','home_team':'🇦🇷 阿根廷',       'away_team':'🇦🇹 奥地利',        'group_name':'J组'},
    {'match_date':'2026-06-23','match_time':'05:00','home_team':'🇫🇷 法国',         'away_team':'🇮🇶 伊拉克',        'group_name':'I组'},
    {'match_date':'2026-06-23','match_time':'08:00','home_team':'🇳🇴 挪威',         'away_team':'🇸🇳 塞内加尔',      'group_name':'I组'},
    {'match_date':'2026-06-23','match_time':'11:00','home_team':'🇯🇴 约旦',         'away_team':'🇩🇿 阿尔及利亚',    'group_name':'J组'},
    # ── 第13比赛日 6月24日 ─────────────────────────────────────
    {'match_date':'2026-06-24','match_time':'01:00','home_team':'🇵🇹 葡萄牙',       'away_team':'🇺🇿 乌兹别克斯坦',  'group_name':'K组'},
    {'match_date':'2026-06-24','match_time':'04:00','home_team':'🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格兰',       'away_team':'🇬🇭 加纳',          'group_name':'L组'},
    {'match_date':'2026-06-24','match_time':'07:00','home_team':'🇵🇦 巴拿马',       'away_team':'🇭🇷 克罗地亚',      'group_name':'L组'},
    {'match_date':'2026-06-24','match_time':'10:00','home_team':'🇨🇴 哥伦比亚',     'away_team':'🇨🇩 刚果（金）',    'group_name':'K组'},
    # ── 第14比赛日 6月25日（A/B/C 第3轮）──────────────────────
    {'match_date':'2026-06-25','match_time':'03:00','home_team':'🇨🇭 瑞士',         'away_team':'🇨🇦 加拿大',        'group_name':'B组'},
    {'match_date':'2026-06-25','match_time':'03:00','home_team':'🇧🇦 波黑',         'away_team':'🇶🇦 卡塔尔',        'group_name':'B组'},
    {'match_date':'2026-06-25','match_time':'06:00','home_team':'🏴󠁧󠁢󠁳󠁣󠁴󠁿 苏格兰',       'away_team':'🇧🇷 巴西',          'group_name':'C组'},
    {'match_date':'2026-06-25','match_time':'06:00','home_team':'🇲🇦 摩洛哥',       'away_team':'🇭🇹 海地',          'group_name':'C组'},
    {'match_date':'2026-06-25','match_time':'09:00','home_team':'🇨🇿 捷克',         'away_team':'🇲🇽 墨西哥',        'group_name':'A组'},
    {'match_date':'2026-06-25','match_time':'09:00','home_team':'🇿🇦 南非',         'away_team':'🇰🇷 韩国',          'group_name':'A组'},
    # ── 第15比赛日 6月26日（D/E/F 第3轮）──────────────────────
    {'match_date':'2026-06-26','match_time':'04:00','home_team':'🇪🇨 厄瓜多尔',     'away_team':'🇩🇪 德国',          'group_name':'E组'},
    {'match_date':'2026-06-26','match_time':'04:00','home_team':'🇨🇼 库拉索',       'away_team':'🇨🇮 科特迪瓦',      'group_name':'E组'},
    {'match_date':'2026-06-26','match_time':'07:00','home_team':'🇯🇵 日本',         'away_team':'🇸🇪 瑞典',          'group_name':'F组'},
    {'match_date':'2026-06-26','match_time':'07:00','home_team':'🇹🇳 突尼斯',       'away_team':'🇳🇱 荷兰',          'group_name':'F组'},
    {'match_date':'2026-06-26','match_time':'10:00','home_team':'🇹🇷 土耳其',       'away_team':'🇺🇸 美国',          'group_name':'D组'},
    {'match_date':'2026-06-26','match_time':'10:00','home_team':'🇵🇾 巴拉圭',       'away_team':'🇦🇺 澳大利亚',      'group_name':'D组'},
    # ── 第16比赛日 6月27日（G/H/I 第3轮）──────────────────────
    {'match_date':'2026-06-27','match_time':'03:00','home_team':'🇳🇴 挪威',         'away_team':'🇫🇷 法国',          'group_name':'I组'},
    {'match_date':'2026-06-27','match_time':'03:00','home_team':'🇸🇳 塞内加尔',     'away_team':'🇮🇶 伊拉克',        'group_name':'I组'},
    {'match_date':'2026-06-27','match_time':'08:00','home_team':'🇨🇻 佛得角',       'away_team':'🇸🇦 沙特阿拉伯',    'group_name':'H组'},
    {'match_date':'2026-06-27','match_time':'08:00','home_team':'🇺🇾 乌拉圭',       'away_team':'🇪🇸 西班牙',        'group_name':'H组'},
    {'match_date':'2026-06-27','match_time':'11:00','home_team':'🇪🇬 埃及',         'away_team':'🇮🇷 伊朗',          'group_name':'G组'},
    {'match_date':'2026-06-27','match_time':'11:00','home_team':'🇳🇿 新西兰',       'away_team':'🇧🇪 比利时',        'group_name':'G组'},
    # ── 第17比赛日 6月28日（J/K/L 第3轮）──────────────────────
    {'match_date':'2026-06-28','match_time':'05:00','home_team':'🇵🇦 巴拿马',       'away_team':'🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格兰',       'group_name':'L组'},
    {'match_date':'2026-06-28','match_time':'05:00','home_team':'🇭🇷 克罗地亚',     'away_team':'🇬🇭 加纳',          'group_name':'L组'},
    {'match_date':'2026-06-28','match_time':'07:30','home_team':'🇨🇴 哥伦比亚',     'away_team':'🇵🇹 葡萄牙',        'group_name':'K组'},
    {'match_date':'2026-06-28','match_time':'07:30','home_team':'🇨🇩 刚果（金）',   'away_team':'🇺🇿 乌兹别克斯坦',  'group_name':'K组'},
    {'match_date':'2026-06-28','match_time':'10:00','home_team':'🇩🇿 阿尔及利亚',   'away_team':'🇦🇹 奥地利',        'group_name':'J组'},
    {'match_date':'2026-06-28','match_time':'10:00','home_team':'🇯🇴 约旦',         'away_team':'🇦🇷 阿根廷',        'group_name':'J组'},
]


# 英文队名 → 我们数据库里的中文队名（不含emoji）
EN_TO_CN = {
    'Mexico': '墨西哥', 'South Africa': '南非',
    'South Korea': '韩国', 'Czech Republic': '捷克', 'Czechia': '捷克',
    'Canada': '加拿大', 'Bosnia and Herzegovina': '波黑', 'Bosnia-Herzegovina': '波黑',
    'United States': '美国', 'USA': '美国',
    'Paraguay': '巴拉圭',
    'Qatar': '卡塔尔', 'Switzerland': '瑞士',
    'Brazil': '巴西', 'Morocco': '摩洛哥',
    'Haiti': '海地', 'Scotland': '苏格兰',
    'Australia': '澳大利亚', 'Turkey': '土耳其', 'Türkiye': '土耳其',
    'Germany': '德国', 'Curaçao': '库拉索', 'Curacao': '库拉索',
    'Ivory Coast': '科特迪瓦', "Cote d'Ivoire": '科特迪瓦',
    'Ecuador': '厄瓜多尔',
    'Netherlands': '荷兰', 'Japan': '日本',
    'Sweden': '瑞典', 'Tunisia': '突尼斯',
    'Spain': '西班牙', 'Cape Verde': '佛得角',
    'Belgium': '比利时', 'Egypt': '埃及',
    'Saudi Arabia': '沙特阿拉伯', 'Uruguay': '乌拉圭',
    'Iran': '伊朗', 'New Zealand': '新西兰',
    'France': '法国', 'Senegal': '塞内加尔',
    'Iraq': '伊拉克', 'Norway': '挪威',
    'Argentina': '阿根廷', 'Algeria': '阿尔及利亚',
    'Austria': '奥地利', 'Jordan': '约旦',
    'Portugal': '葡萄牙',
    'Democratic Republic of the Congo': '刚果（金）',
    'DR Congo': '刚果（金）', 'Congo DR': '刚果（金）',
    'Uzbekistan': '乌兹别克斯坦', 'Colombia': '哥伦比亚',
    'England': '英格兰', 'Croatia': '克罗地亚',
    'Ghana': '加纳', 'Panama': '巴拿马',
}

ESPN_API = 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260612-20260719'

def sync_scores():
    """从 ESPN 拉取实时比分，自动更新未结算的比赛。返回更新场数。"""
    try:
        resp = http.get(ESPN_API, timeout=15)
        events = resp.json().get('events', [])
    except Exception:
        return 0

    updated = 0
    for e in events:
        comp = e['competitions'][0]
        if not comp['status']['type'].get('completed'):
            continue
        competitors = comp['competitors']
        home_c = next((x for x in competitors if x['homeAway'] == 'home'), None)
        away_c = next((x for x in competitors if x['homeAway'] == 'away'), None)
        if not home_c or not away_c:
            continue
        home_cn = EN_TO_CN.get(home_c['team']['displayName'])
        away_cn = EN_TO_CN.get(away_c['team']['displayName'])
        if not home_cn or not away_cn:
            continue
        try:
            h, a = int(home_c['score']), int(away_c['score'])
        except (ValueError, TypeError):
            continue
        match = fetch_one(
            "SELECT * FROM matches WHERE home_team LIKE :h AND away_team LIKE :a AND home_score IS NULL",
            {'h': f'% {home_cn}', 'a': f'% {away_cn}'}
        )
        if not match:
            continue
        run('UPDATE matches SET home_score=:h, away_score=:a WHERE id=:id',
            {'h': h, 'a': a, 'id': match['id']})
        settle_match(match['id'])
        updated += 1
    return updated


def init_db():
    schema = SQLITE_SCHEMA if IS_SQLITE else PG_SCHEMA
    with engine.begin() as c:
        for stmt in schema:
            c.execute(text(stmt))

    if fetch_one('SELECT COUNT(*) AS n FROM users')['n'] == 0:
        with engine.begin() as c:
            c.execute(text(
                'INSERT INTO users (username, display_name, password, is_admin) '
                'VALUES (:username, :display_name, :password, :is_admin)'
            ), USERS_SEED)

    if fetch_one('SELECT COUNT(*) AS n FROM matches')['n'] == 0:
        with engine.begin() as c:
            c.execute(text(
                'INSERT INTO matches (match_date, match_time, home_team, away_team, group_name) '
                'VALUES (:match_date, :match_time, :home_team, :away_team, :group_name)'
            ), MATCHES_SEED)


# ── 计分 ───────────────────────────────────────────────────────────────────
def calc_points(home_score, away_score, pred_home, pred_away):
    if pred_home == home_score and pred_away == away_score:
        return 3
    sign = lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
    return 1 if sign(home_score - away_score) == sign(pred_home - pred_away) else 0


def settle_match(match_id):
    with engine.begin() as c:
        match = c.execute(text('SELECT * FROM matches WHERE id = :id'), {'id': match_id}).mappings().first()
        if not match or match['home_score'] is None or match['settled']:
            return
        preds = c.execute(text('SELECT * FROM predictions WHERE match_id = :mid'), {'mid': match_id}).mappings().all()
        for p in preds:
            if p['points'] is not None:
                continue
            pts = calc_points(match['home_score'], match['away_score'], p['pred_home'], p['pred_away'])
            c.execute(text('UPDATE predictions SET points = :pts WHERE id = :id'), {'pts': pts, 'id': p['id']})
            c.execute(text('UPDATE users SET total_points = total_points + :pts WHERE id = :id'), {'pts': pts, 'id': p['user_id']})
        c.execute(text('UPDATE matches SET settled = 1 WHERE id = :id'), {'id': match_id})


# ── Flask ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'public'), static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'wc2026-prediction-secret-py')


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify(error='请先登录'), 401
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify(error='请先登录'), 401
        user = fetch_one('SELECT * FROM users WHERE id = :id', {'id': session['user_id']})
        if not user or not user['is_admin']:
            return jsonify(error='无权限'), 403
        return f(*args, **kwargs)
    return wrapper


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.get('/api/me')
def api_me():
    if 'user_id' not in session:
        return jsonify(user=None)
    user = fetch_one(
        'SELECT id, username, display_name, is_admin, total_points FROM users WHERE id = :id',
        {'id': session['user_id']}
    )
    return jsonify(user=user)


@app.post('/api/login')
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='请输入你的名字'), 400
    user = fetch_one('SELECT * FROM users WHERE display_name = :n', {'n': name})
    if not user:
        return jsonify(error='名字不存在，请确认后重试'), 401
    session['user_id'] = user['id']
    return jsonify(user={k: user[k] for k in ('id', 'username', 'display_name', 'is_admin', 'total_points')})


@app.post('/api/logout')
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/api/standings')
def api_standings():
    return jsonify(standings=fetch_all(
        'SELECT id, display_name, total_points FROM users WHERE is_admin = 0 ORDER BY total_points DESC, id ASC'
    ))


@app.get('/api/match-days')
def api_match_days():
    return jsonify(days=fetch_all(
        "SELECT match_date, COUNT(*) AS total, "
        "SUM(CASE WHEN settled=1 THEN 1 ELSE 0 END) AS settled_count "
        "FROM matches GROUP BY match_date ORDER BY match_date ASC"
    ))


def build_day(date):
    matches = fetch_all('SELECT * FROM matches WHERE match_date = :d ORDER BY match_time ASC, id ASC', {'d': date})
    players = fetch_all('SELECT id, display_name, username FROM users WHERE is_admin = 0 ORDER BY id ASC')
    predictions = []
    if matches:
        ids = ','.join(str(m['id']) for m in matches)
        predictions = fetch_all(
            f'SELECT p.*, u.display_name, u.username FROM predictions p '
            f'JOIN users u ON p.user_id = u.id WHERE p.match_id IN ({ids})'
        )
    return dict(date=date, matches=matches, players=players, predictions=predictions)


@app.get('/api/current-day')
def api_current_day():
    from datetime import datetime, timezone, timedelta
    # 使用北京时间（UTC+8）确定今天
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    has_today = fetch_one('SELECT 1 AS x FROM matches WHERE match_date = :d LIMIT 1', {'d': today})
    if has_today:
        target = today
    else:
        nxt = fetch_one(
            'SELECT DISTINCT match_date FROM matches WHERE match_date > :d ORDER BY match_date ASC LIMIT 1',
            {'d': today}
        )
        target = nxt['match_date'] if nxt else today
    return jsonify(build_day(target))


@app.get('/api/day/<date>')
def api_day(date):
    return jsonify(build_day(date))


@app.post('/api/predict')
@require_auth
def api_predict():
    data = request.get_json(force=True, silent=True) or {}
    match_id, pred_home, pred_away = data.get('match_id'), data.get('pred_home'), data.get('pred_away')
    if match_id is None or pred_home is None or pred_away is None:
        return jsonify(error='参数缺失'), 400

    me = fetch_one('SELECT is_admin FROM users WHERE id = :id', {'id': session['user_id']})
    target_uid = session['user_id']
    if data.get('user_id'):
        if not me or not me['is_admin']:
            return jsonify(error='无权限'), 403
        target_uid = int(data['user_id'])
    elif me and me['is_admin']:
        return jsonify(error='管理员不参与预测'), 403

    match = fetch_one('SELECT * FROM matches WHERE id = :id', {'id': match_id})
    if not match:
        return jsonify(error='比赛不存在'), 404
    if match['settled']:
        return jsonify(error='比赛已结算，不能修改预测'), 400

    try:
        h, a = int(pred_home), int(pred_away)
        if h < 0 or a < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error='预测比分无效'), 400

    with engine.begin() as c:
        match = c.execute(text('SELECT * FROM matches WHERE id = :id'), {'id': match_id}).mappings().first()
        new_pts = None
        if match and match['home_score'] is not None:
            new_pts = calc_points(match['home_score'], match['away_score'], h, a)

        old_pred = c.execute(
            text('SELECT points FROM predictions WHERE user_id = :uid AND match_id = :mid'),
            {'uid': target_uid, 'mid': match_id}
        ).mappings().first()
        old_pts = old_pred['points'] if old_pred else None

        # 积分差值更新
        delta = (new_pts or 0) - (old_pts or 0)
        if delta != 0:
            c.execute(text('UPDATE users SET total_points = total_points + :d WHERE id = :id'),
                      {'d': delta, 'id': target_uid})

        c.execute(text("""
            INSERT INTO predictions (user_id, match_id, pred_home, pred_away, points)
            VALUES (:uid, :mid, :ph, :pa, :pts)
            ON CONFLICT(user_id, match_id) DO UPDATE SET
                pred_home = excluded.pred_home,
                pred_away = excluded.pred_away,
                points = excluded.points
        """), {'uid': target_uid, 'mid': match_id, 'ph': h, 'pa': a, 'pts': new_pts})
    return jsonify(ok=True)


@app.post('/api/set-points')
@require_auth
def api_set_points():
    data = request.get_json(force=True, silent=True) or {}
    try:
        pts = int(data.get('points'))
        if pts < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error='积分无效'), 400
    target_id = session['user_id']
    if data.get('user_id'):
        me = fetch_one('SELECT is_admin FROM users WHERE id = :id', {'id': session['user_id']})
        if not me or not me['is_admin']:
            return jsonify(error='无权限'), 403
        target_id = int(data['user_id'])
    run('UPDATE users SET total_points = :pts WHERE id = :id', {'pts': pts, 'id': target_id})
    return jsonify(ok=True)


@app.post('/api/admin/result')
@require_auth
def api_admin_result():
    data = request.get_json(force=True, silent=True) or {}
    match_id, home_score, away_score = data.get('match_id'), data.get('home_score'), data.get('away_score')
    if match_id is None or home_score is None or away_score is None:
        return jsonify(error='参数缺失'), 400
    if not fetch_one('SELECT 1 AS x FROM matches WHERE id = :id', {'id': match_id}):
        return jsonify(error='比赛不存在'), 404
    try:
        h, a = int(home_score), int(away_score)
        if h < 0 or a < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error='比分无效'), 400
    run('UPDATE matches SET home_score = :h, away_score = :a WHERE id = :id', {'h': h, 'a': a, 'id': match_id})
    settle_match(match_id)
    return jsonify(ok=True)


@app.post('/api/sync-scores')
@require_auth
def api_sync_scores():
    updated = sync_scores()
    return jsonify(ok=True, updated=updated)


@app.post('/api/admin/reset-seed')
@require_admin
def api_admin_reset_seed():
    with engine.begin() as c:
        c.execute(text('DELETE FROM predictions'))
        c.execute(text('DELETE FROM matches'))
        c.execute(text(
            'INSERT INTO matches (match_date, match_time, home_team, away_team, group_name) '
            'VALUES (:match_date, :match_time, :home_team, :away_team, :group_name)'
        ), MATCHES_SEED)
    return jsonify(ok=True, message=f'已重置 {len(MATCHES_SEED)} 场比赛（所有预测已清空）')


@app.post('/api/admin/clear-result')
@require_auth
def api_admin_clear():
    data = request.get_json(force=True, silent=True) or {}
    match_id = data.get('match_id')
    if not match_id:
        return jsonify(error='参数缺失'), 400
    match = fetch_one('SELECT * FROM matches WHERE id = :id', {'id': match_id})
    if not match:
        return jsonify(error='比赛不存在'), 404
    with engine.begin() as c:
        if match['settled']:
            preds = c.execute(text('SELECT * FROM predictions WHERE match_id = :mid'), {'mid': match_id}).mappings().all()
            for p in preds:
                if p['points'] is not None:
                    c.execute(text('UPDATE users SET total_points = total_points - :pts WHERE id = :id'),
                              {'pts': p['points'], 'id': p['user_id']})
                    c.execute(text('UPDATE predictions SET points = NULL WHERE id = :id'), {'id': p['id']})
        c.execute(text('UPDATE matches SET home_score = NULL, away_score = NULL, settled = 0 WHERE id = :id'),
                  {'id': match_id})
    return jsonify(ok=True)


def _bg_sync():
    """后台线程：每 60 秒自动同步一次真实比分，无需用户手动触发。"""
    while True:
        time.sleep(60)
        try:
            sync_scores()
        except Exception:
            pass

# ── 启动 ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    threading.Thread(target=_bg_sync, daemon=True).start()
    print(f'\n🏆 2026美加墨世界杯预测系统已启动')
    print(f'   访问: http://localhost:{PORT}\n')
    print('账号: player1~4 / 1234  |  admin / admin888\n')
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    # gunicorn 启动时也初始化数据库
    init_db()
    threading.Thread(target=_bg_sync, daemon=True).start()
