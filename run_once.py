# run_once.py
import os
import json
from admin_bot import AdminBot

def main():
    config = {}
    if os.path.exists("config.json"):
        with open("config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)

    username = os.getenv("BOT_USERNAME") or config.get("username")
    password = os.getenv("BOT_PASSWORD") or config.get("password")
    api_key = os.getenv("DEEPSEEK_API_KEY") or config.get("deepseek_api_key")

    if not username or not password or not api_key:
        print("错误：缺少必要配置 (username, password, deepseek_api_key)")
        return

    bot_config = {
        "username": username,
        "password": password,
        "target_categories": [2, 5],
        "skip_latest": 5,
        "max_threads": 30,
        "post_interval_minutes": 1,
        "content_snippet_length": 200,
        "exempt_thread_ids": [15669, 28348, 27305, 27115, 11411, 3448],
        "login_retries": 3,
    }
    bot = AdminBot(bot_config, api_key)
    bot.run(continuous=False)   # 单次运行

if __name__ == "__main__":
    main()
