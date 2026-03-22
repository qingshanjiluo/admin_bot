# admin_bot.py
import time
import os
import json
import signal
import sys
from datetime import datetime
from login import BBSTurkeyBotLogin
from post import BBSPoster
from common import BASE_URL
from deepseek_client import DeepSeekClient

class AdminBot:
    def __init__(self, config, api_key):
        self.config = config
        self.username = config.get("username")
        self.password = config.get("password")
        self.login_retries = config.get("login_retries", 50)
        self.target_categories = config.get("target_categories", [2, 5])
        self.admin_category = 15
        self.skip_latest = config.get("skip_latest", 5)
        self.max_threads = config.get("max_threads", 30)
        self.post_interval_minutes = config.get("post_interval_minutes", 1)
        self.content_snippet_length = config.get("content_snippet_length", 200)
        self.exempt_ids = set(config.get("exempt_thread_ids", [15669, 28348, 27305, 27115, 11411, 3448]))
        self.ai = DeepSeekClient(api_key=api_key)
        self.background = self._load_file("mk48.txt")
        self.rules = self._load_file("rules.txt")
        self.sensitive_words = self._load_sensitive_words()
        self.session = None
        self.token = None
        self.user_id = None
        self.warned_ids = set()
        self.daily_log = []          # 本轮扫描日志
        self.daily_violations = []   # 本轮发现的违规帖子详情
        self.loop_count = 0
        self.pinned_skipped = set()
        self.running = True
        self._load_state()
        self.warned_ids.update(self.exempt_ids)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _load_file(self, fname):
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return ""

    def _load_sensitive_words(self):
        words = []
        try:
            with open("mgc.txt", 'r', encoding='utf-8') as f:
                words = [line.strip() for line in f if line.strip()]
        except:
            pass
        return words

    def _contains_sensitive(self, text):
        if not text or not self.sensitive_words:
            return False
        text_lower = text.lower()
        for word in self.sensitive_words:
            if word and word.lower() in text_lower:
                return word
        return False

    def _load_state(self):
        if os.path.exists("processed_admin.json"):
            with open("processed_admin.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.warned_ids = set(data.get("warned_ids", []))

    def _save_state(self):
        data = {"warned_ids": list(self.warned_ids)}
        with open("processed_admin.json", "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _signal_handler(self, sig, frame):
        print("\n[管理员] 正在保存状态...")
        self.running = False
        self._save_state()
        sys.exit(0)

    def login(self):
        print("[登录] 正在登录论坛...")
        login_bot = BBSTurkeyBotLogin(BASE_URL, self.username, self.password, self.login_retries)
        ok, res, sess = login_bot.login_with_retry()
        if ok:
            self.session = sess
            self.token = res['data']['token']
            self.user_id = res['data']['id']
            return True
        return False

    def check_violation(self, text):
        hit = self._contains_sensitive(text)
        if hit:
            return True, "political", f"命中敏感词: {hit}"
        violation, vtype, reason = self.ai.judge_violation(text, self.background, self.rules)
        if vtype is None:
            return False, None, "AI调用失败"
        return violation, vtype, reason

    def scan_threads(self, poster):
        scanned = 0
        violations = 0
        self.daily_log = []
        self.daily_violations = []
        for cat_id in self.target_categories:
            if not self.running:
                break
            print(f"[扫描] 板块 {cat_id}")
            offset = 0
            total = 0
            while total < self.max_threads:
                if not self.running:
                    break
                threads = poster.get_threads(self.token, cat_id, page_limit=self.max_threads, page_offset=offset)
                if not threads:
                    break
                if len(threads) > self.skip_latest:
                    process = threads[self.skip_latest:]
                    print(f"   跳过本页最新 {self.skip_latest} 个帖子")
                else:
                    process = []
                for t in process:
                    tid = t['id']
                    if tid in self.warned_ids:
                        continue
                    if t.get('is_pinned', False):
                        if tid not in self.pinned_skipped:
                            print(f"   跳过置顶帖: {t['title'][:30]}")
                            self.pinned_skipped.add(tid)
                        continue
                    if t.get('user_id') == self.user_id:
                        self.warned_ids.add(tid)
                        scanned += 1
                        continue
                    print(f"   处理: {t['title'][:30]} (ID: {tid})")
                    full = f"{t['title']}\n{t.get('content','')}"
                    violation, vtype, reason = self.check_violation(full)
                    if vtype is None:
                        print(f"      AI失败，稍后重试")
                        continue
                    snippet = full[:self.content_snippet_length] + ("..." if len(full) > self.content_snippet_length else "")
                    self.daily_log.append({
                        "time": datetime.now().isoformat(),
                        "thread_id": tid,
                        "title": t['title'],
                        "snippet": snippet,
                        "category": cat_id,
                        "violation": violation,
                        "type": vtype if violation else None
                    })
                    if violation and vtype != 'ad':
                        self.daily_violations.append({
                            "time": datetime.now().isoformat(),
                            "thread_id": tid,
                            "title": t['title'],
                            "snippet": snippet,
                            "type": vtype,
                            "reason": reason,        # 完整的AI判定语句
                            "link": f"https://mk48by049.mbbs.cc/#/thread/detail/{tid}"
                        })
                        violations += 1
                        print(f"      ⚠️ 违规！类型: {vtype}, 原因: {reason[:100]}...")
                    elif violation and vtype == 'ad':
                        print(f"      [广告忽略]")
                    else:
                        print(f"      ✅ 合规")
                    self.warned_ids.add(tid)
                    scanned += 1
                    time.sleep(0.5)
                total += len(threads)
                offset += 1
                if len(threads) < self.max_threads:
                    break
        return scanned, violations

    def _build_report_section(self, violations_sublist, start_idx, total_parts, overall):
        content = f"## 📊 {overall['date']} 本轮违规统计 (第{start_idx}部分/共{total_parts}部分)\n\n"
        content += f"- 检查帖子总数：{overall['total_scanned']}\n"
        content += f"- 发现违规帖子：{overall['total_violations']}\n"
        content += f"- 累计审查帖子总数：{overall['total_checked']}\n"
        content += f"- 本轮序号：{overall['loop_count']}\n\n"
        content += f"### ⚠️ 本部分违规帖子（{len(violations_sublist)}个）\n"
        for idx, v in enumerate(violations_sublist, 1):
            content += f"{idx}. [{v['title']}]({v['link']})\n"
            content += f"   - **类型**：{v['type']}\n"
            content += f"   - **判定**：{v['reason']}\n"          # 完整AI判定语句
            content += f"   - **原文摘要**：{v.get('snippet', '无')}\n\n"
        content += f"\n---\n*报告由最中幻想天眼管理机器人自动生成*"
        return content

    def _post_with_retry(self, poster, title, content, retry_login=True):
        success, _ = poster.create_thread(self.token, self.admin_category, title, content)
        if success:
            print(f"[日报] 成功发布")
            return True

        print("[日报] 发布失败，将在30秒后重试...")
        filename = f"failed_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"标题：{title}\n\n")
                f.write(content)
            print(f"[日报] 内容已保存至本地文件：{os.path.abspath(filename)}")
        except Exception as e:
            print(f"[日报] 保存本地文件失败：{e}")

        time.sleep(30)
        if retry_login:
            print("[日报] 尝试重新登录...")
            if self.login():
                print("[日报] 重新登录成功，使用新 token 重试发布")
                poster = BBSPoster(self.session, BASE_URL)
            else:
                print("[日报] 重新登录失败，仍使用原 token 重试")

        success2, _ = poster.create_thread(self.token, self.admin_category, title, content)
        if success2:
            print(f"[日报] 重试成功，已发布")
            return True
        else:
            print(f"[日报] 重试仍失败")
            return False

    def post_daily_report(self, poster):
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_scanned = len(self.daily_log)
        total_violations = len(self.daily_violations)
        total_checked = len(self.warned_ids)

        # 生成可爱总结
        summary = self.ai.generate_summary({
            'total_scanned': total_scanned,
            'total_violations': total_violations,
            'total_checked': total_checked,
            'loop_count': self.loop_count
        })

        if not self.daily_violations:
            title = f"【管理日报】{today} 第{self.loop_count}次扫描 - 违规 0 个"
            content = f"## 📊 {today} 本轮扫描统计\n\n"
            content += f"- 检查帖子总数：{total_scanned}\n"
            content += f"- 发现违规帖子：0\n"
            content += f"- 累计审查帖子总数：{total_checked}\n"
            content += f"- 本轮序号：{self.loop_count}\n\n"
            content += "本轮无违规帖子。\n"
            content += f"\n---\n**今日小结**：{summary}\n"
            content += f"\n*报告由最中幻想天眼管理机器人自动生成*"
            self._post_with_retry(poster, title, content, retry_login=True)
            return

        overall = {
            'date': today,
            'total_scanned': total_scanned,
            'total_violations': total_violations,
            'total_checked': total_checked,
            'loop_count': self.loop_count
        }

        full_content = self._build_report_section(self.daily_violations, 1, 1, overall)
        if len(full_content) <= 4000:
            full_content += f"\n\n---\n**今日小结**：{summary}\n"
            title = f"【管理日报】{today} 第{self.loop_count}次扫描 - 违规 {total_violations} 个"
            self._post_with_retry(poster, title, full_content, retry_login=True)
            return

        # 分片
        print(f"[日报] 内容过长，将拆分为多个帖子发布")
        slices = []
        remaining = self.daily_violations.copy()
        part = 1
        while remaining:
            best = 1
            for cnt in range(1, len(remaining)+1):
                test = self._build_report_section(remaining[:cnt], part, 0, overall)
                if len(test) <= 4000:
                    best = cnt
                else:
                    break
            part_violations = remaining[:best]
            slices.append(part_violations)
            remaining = remaining[best:]
            part += 1

        total_parts = len(slices)
        for idx, part_violations in enumerate(slices, 1):
            part_content = self._build_report_section(part_violations, idx, total_parts, overall)
            if idx == total_parts:
                part_content += f"\n\n---\n**今日小结**：{summary}\n"
            part_title = f"【管理日报】{today} 第{self.loop_count}次扫描 - 违规 {total_violations} 个（第{idx}部分/共{total_parts}部分）"
            retry_login = (idx == 1)
            self._post_with_retry(poster, part_title, part_content, retry_login=retry_login)
            if idx < total_parts:
                time.sleep(self.post_interval_minutes * 60)

    def run(self, continuous=False):
        print("[管理员机器人] 启动")
        if not self.login():
            print("登录失败，退出")
            return
        poster = BBSPoster(self.session, BASE_URL)
        self.loop_count = 0
        try:
            while self.running:
                self.loop_count += 1
                print(f"\n[循环] 第 {self.loop_count} 次扫描 - {datetime.now()}")
                scanned, violations = self.scan_threads(poster)
                print(f"[统计] 本轮扫描: 新增记录 {scanned} 个帖子，发现违规 {violations} 个")
                self.post_daily_report(poster)
                self._save_state()
                if not continuous or not self.running:
                    break
                # 连续模式下等待间隔（单次模式不等待）
                for _ in range(self.config.get("scan_interval", 7200)):
                    if not self.running:
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            print("\n[中断] 用户中断")
        finally:
            self._save_state()
            print("[完成] 状态已保存，机器人退出")
