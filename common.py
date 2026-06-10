# common.py
import os

# 论坛 API 根地址（注意：不是页面地址，是 API 地址）
BASE_URL = "https://mbbs.zdjl.site/mk48by049.mbbs.cc"

DEFAULT_ADMIN_CONFIG = {
    "username": "",
    "password": "",
    "target_categories": [2, 5],
    "scan_interval": 7200,
    "skip_latest": 5,
    "max_threads": 30,
    "daily_report_interval": 86400,
    "post_interval_minutes": 1,
    "content_snippet_length": 200,
    "exempt_thread_ids": [15669, 28348, 27305, 27115, 11411, 3448],
}

DEFAULT_COMMENT_CONFIG = {
    "username": "",
    "password": "",
    "target_categories": [2],
    "scan_interval": 300,
    "reply_interval": 10,
    "daily_post_limit": 5,
    "comment_ratio": 0.5,
    "promote_probability": 0.2,
    "style_file": "zzhx.txt",
    "domains": ["neonlink.free.nf"],
}

DEFAULT_POSTER_CONFIG = {
    "username": "",
    "password": "",
    "target_categories": [2],
    "post_interval": 3600,
    "daily_limit": 3,
    "style_file": "zzhx.txt",
    "domains": ["neonlink.free.nf"],
}

def load_config(file):
    if os.path.exists(file):
        import json
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}
