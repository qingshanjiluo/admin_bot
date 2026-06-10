# admin_bot.py
import time
import os
import json
import signal
import sys
import re
from datetime import datetime, date
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
        self.scan_interval = config.get("scan_interval", 7200)
        self.target_categories = config.get("target_categories", [2, 5])
        self.admin_category = 15
        self.skip_latest = config.get("skip_latest", 5)
        self.max_threads = config.get("max_threads", 30)
        self.daily_report_interval = config.get("daily_report_interval", 86400)
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
        self.warned_comment_ids = set()
        self.daily_log = []
        self.daily_violations = []
        self.loop_count = 0
        self.last_report_time = None
        self.pinned_skipped = set()
        self.running = True
        
        self._load_state()
        self.warned_ids.update(self.exempt_ids)
        signal.signal(signal.SIGINT, self._signal_handler)

    # ---------- 辅助函数 ----------
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
                self.warned_comment_ids = set(data.get("warned_comment_ids", []))
                self.daily_log = data.get("daily_log", [])
                self.daily_violations = data.get("daily_violations", [])

    def _save_state(self):
        data = {
            "warned_ids": list(self.warned_ids),
            "warned_comment_ids": list(self.warned_comment_ids),
            "daily_log": self.daily_log[-1000:],
            "daily_violations": self.daily_violations[-500:]
        }
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
            self.poster = BBSPoster(self.session, BASE_URL)
            self.poster.user_id = self.user_id
            return True
        return False

    # ---------- 违规检测 ----------
    def check_violation(self, text):
        hit = self._contains_sensitive(text)
        if hit:
            return True, "political", f"命中敏感词: {hit}"
        violation, vtype, reason = self.ai.judge_violation(text, self.background, self.rules)
        if vtype is None:
            return False, None, "AI调用失败"
        return violation, vtype, reason

    def check_violation_with_context(self, thread_text, comments_text):
        """综合帖子内容和评论判断帖子是否违规"""
        hit = self._contains_sensitive(thread_text)
        if hit:
            return True, "political", f"命中敏感词: {hit}"
        combined = f"【帖子内容】\n{thread_text}\n\n【评论内容（可能包含违规）】\n{comments_text}"
        violation, vtype, reason = self.ai.judge_violation(combined, self.background, self.rules)
        if vtype is None:
            return False, None, "AI调用失败"
        return violation, vtype, reason

    # ---------- 发送警告（有温度版）----------
    def send_warning_to_thread(self, thread_id, violation_type, reason):
        short_reason = reason[:80] + ("..." if len(reason) > 80 else "")
        warn_msg = f"您好，您的帖子可能违反了论坛规则（{violation_type}）。{short_reason} 请遵守版规，感谢理解与支持。如有疑问可联系管理员。"
        success = self.poster.create_comment(self.token, thread_id, warn_msg)
        if success:
            print(f"✅ 已对帖子 {thread_id} 发出警告")
        else:
            print(f"❌ 警告发布失败，帖子 {thread_id}")
        return success

    def send_warning_to_comment(self, post_id, violation_type, reason):
        short_reason = reason[:80] + ("..." if len(reason) > 80 else "")
        warn_msg = f"您好，您的评论可能违反了论坛规则（{violation_type}）。{short_reason} 请遵守版规，感谢理解与支持。如有疑问可联系管理员。"
        success = self.poster.reply_to_comment(self.token, post_id, warn_msg)
        if success:
            print(f"✅ 已对评论 {post_id} 发出警告")
        else:
            print(f"❌ 警告发布失败，评论 {post_id}")
        return success

    # ---------- 递归获取评论 ----------
    def _get_all_comments(self, thread_id):
        comments = []
        first_level = self.poster.get_post_comments(self.token, thread_id)
        for c in first_level:
            comments.append(c)
            replies = self._get_replies(c['id'])
            comments.extend(replies)
        return comments

    def _get_replies(self, post_id):
        replies = []
        resp = self.poster.get_comment_replies(self.token, post_id)
        for r in resp:
            replies.append(r)
            deeper = self._get_replies(r['id'])
            replies.extend(deeper)
        return replies

    # ---------- 扫描单个帖子及其所有评论 ----------
    def scan_thread_and_comments(self, thread):
        tid = thread['id']
        title = thread['title']
        content = thread.get('content', '')
        full = f"{title}\n{content}"
        
        comments = self._get_all_comments(tid)
        comments_text = ""
        for idx, c in enumerate(comments[:20]):
            c_content = c.get('content', '')[:150]
            comments_text += f"评论{idx+1}: {c_content}\n"
        
        is_violation, vtype, reason = self.check_violation_with_context(full, comments_text)
        snippet = full[:self.content_snippet_length] + ("..." if len(full) > self.content_snippet_length else "")
        
        self.daily_log.append({
            "time": datetime.now().isoformat(),
            "type": "thread",
            "id": tid,
            "title": title,
            "snippet": snippet,
            "violation": is_violation,
            "vtype": vtype if is_violation else None
        })
        
        if is_violation and vtype != 'ad':
            self.daily_violations.append({
                "time": datetime.now().isoformat(),
                "type": "thread",
                "id": tid,
                "title": title,
                "snippet": snippet,
                "vtype": vtype,
                "reason": reason,
                "link": f"https://mk48by049.mbbs.cc/#/thread/detail/{tid}"
            })
            print(f"      ⚠️ 帖子违规！类型: {vtype}, 原因: {reason[:100]}...")
            self.send_warning_to_thread(tid, vtype, reason)
        else:
            print(f"      ✅ 帖子合规")
        
        self.warned_ids.add(tid)
        
        for comment in comments:
            cid = comment['id']
            if cid in self.warned_comment_ids:
                continue
            c_content = comment.get('content', '')
            c_author = comment.get('user', {}).get('nickname', '未知')
            is_violation_c, vtype_c, reason_c = self.check_violation(c_content)
            snippet_c = c_content[:self.content_snippet_length] + ("..." if len(c_content) > self.content_snippet_length else "")
            self.daily_log.append({
                "time": datetime.now().isoformat(),
                "type": "comment",
                "id": cid,
                "thread_id": tid,
                "author": c_author,
                "snippet": snippet_c,
                "violation": is_violation_c,
                "vtype": vtype_c if is_violation_c else None
            })
            if is_violation_c and vtype_c != 'ad':
                self.daily_violations.append({
                    "time": datetime.now().isoformat(),
                    "type": "comment",
                    "id": cid,
                    "thread_id": tid,
                    "author": c_author,
                    "snippet": snippet_c,
                    "vtype": vtype_c,
                    "reason": reason_c,
                    "link": f"https://mk48by049.mbbs.cc/#/thread/detail/{tid}"
                })
                print(f"      ⚠️ 评论违规！类型: {vtype_c}, 原因: {reason_c[:100]}...")
                self.send_warning_to_comment(cid, vtype_c, reason_c)
            else:
                print(f"      ✅ 评论合规")
            self.warned_comment_ids.add(cid)
            time.sleep(0.3)
        
        return 1

    # ---------- 扫描板块 ----------
    def scan_threads(self):
        scanned = 0
        violations = 0
        for cat_id in self.target_categories:
            if not self.running:
                break
            print(f"[扫描] 板块 {cat_id}")
            offset = 0
            total = 0
            while total < self.max_threads:
                if not self.running:
                    break
                threads = self.poster.get_threads(self.token, cat_id, page_limit=self.max_threads, page_offset=offset)
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
                    if not t.get('content'):
                        detail = self.poster.get_thread_detail(self.token, tid)
                        if detail:
                            t['content'] = detail.get('content', '')
                    self.scan_thread_and_comments(t)
                    scanned += 1
                total += len(threads)
                offset += 1
                if len(threads) < self.max_threads:
                    break
        return scanned, len([v for v in self.daily_violations if v['time'].startswith(date.today().isoformat())])

    # ---------- 日报相关 ----------
    def _build_report_section(self, violations_sublist, start_idx, total_parts, overall):
        content = f"## 📊 {overall['today']} 违规统计 (第{start_idx}部分/共{total_parts}部分)\n\n"
        content += f"- 今日发现违规项：{overall['total_violations']}\n"
        content += f"- 累计审查帖子数：{overall['total_checked']}\n"
        content += f"- 当前循环次数：{overall['loop_count']}\n\n"
        content += f"### ⚠️ 本部分违规内容（{len(violations_sublist)}个）\n"
        for idx, v in enumerate(violations_sublist, 1):
            if v['type'] == 'thread':
                content += f"{idx}. [帖子] [{v['title']}]({v['link']})\n"
                content += f"   - **类型**：{v['vtype']}\n"
                content += f"   - **原因**：{v['reason']}\n"
                content += f"   - **原文摘要**：{v.get('snippet', '无')}\n\n"
            else:
                content += f"{idx}. [评论] 作者：{v['author']} 在帖子ID {v['thread_id']} 中\n"
                content += f"   - 评论内容摘要：{v['snippet']}\n"
                content += f"   - **类型**：{v['vtype']}\n"
                content += f"   - **原因**：{v['reason']}\n\n"
        content += f"\n---\n*报告由最中幻想天眼管理机器人自动生成*"
        return content

    def _post_with_retry(self, title, content):
        success, _ = self.poster.create_thread(self.token, self.admin_category, title, content)
        if success:
            print(f"[日报] 成功发布")
            return True
        print("[日报] 发布失败，30秒后重试...")
        time.sleep(30)
        if self.login():
            success2, _ = self.poster.create_thread(self.token, self.admin_category, title, content)
            if success2:
                print("[日报] 重试成功")
                return True
        filename = f"failed_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"标题：{title}\n\n{content}")
        print(f"[日报] 已保存至 {filename}")
        return False

    def post_daily_report(self):
        today = date.today().isoformat()
        today_violations = [v for v in self.daily_violations if v['time'].startswith(today)]
        total_violations = len(today_violations)
        total_checked = len(self.warned_ids) + len(self.warned_comment_ids)

        type_dist = {}
        for v in today_violations:
            t = v['vtype']
            type_dist[t] = type_dist.get(t, 0) + 1

        if total_violations > 0:
            summary = self.ai.generate_summary({
                'total_checked': total_checked,
                'total_violations': total_violations,
                'type_distribution': type_dist,
                'loop_count': self.loop_count
            })
        else:
            summary = "今日无违规内容，大家表现不错！继续加油~ ✨"

        overall_stats = {
            'today': today,
            'total_violations': total_violations,
            'total_checked': total_checked,
            'loop_count': self.loop_count
        }

        full_content = self._build_report_section(today_violations, 1, 1, overall_stats)
        if len(full_content) <= 4000:
            full_content += f"\n\n---\n**今日小结**：{summary}\n"
            title = f"【管理日报】{today} 第{self.loop_count}次循环 - 违规 {total_violations} 项"
            self._post_with_retry(title, full_content)
            self.last_report_time = time.time()
            return

        print(f"[日报] 内容过长，将拆分为多个帖子发布")
        slices = []
        remaining = today_violations.copy()
        part = 1
        while remaining:
            best = 1
            for cnt in range(1, len(remaining)+1):
                test = self._build_report_section(remaining[:cnt], part, 0, overall_stats)
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
            part_content = self._build_report_section(part_violations, idx, total_parts, overall_stats)
            if idx == total_parts:
                part_content += f"\n\n---\n**今日小结**：{summary}\n"
            part_title = f"【管理日报】{today} 第{self.loop_count}次循环 - 违规 {total_violations} 项（第{idx}部分/共{total_parts}部分）"
            self._post_with_retry(part_title, part_content)
            if idx < total_parts:
                time.sleep(self.post_interval_minutes * 60)
        self.last_report_time = time.time()

    def _should_post_report(self, now):
        if self.daily_report_interval == 0:
            return True
        if self.last_report_time is None:
            return True
        return (now - self.last_report_time) >= self.daily_report_interval

    # ---------- 处理管理指令 ----------
    def process_admin_commands(self):
        threads = self.poster.get_threads(self.token, category_id=self.admin_category, page_limit=10)
        if not threads:
            return
        for thread in threads:
            if "管理日报" not in thread.get('title', ''):
                continue
            thread_id = thread['id']
            comments = self.poster.get_post_comments(self.token, thread_id)
            for comment in comments:
                content = comment.get('content', '')
                match = re.search(r'删[除掉]第(\d+)[个\s]*违规帖子', content)
                if match:
                    idx = int(match.group(1))
                    today = date.today().isoformat()
                    today_violations = [v for v in self.daily_violations if v['time'].startswith(today) and v['type'] == 'thread']
                    if 1 <= idx <= len(today_violations):
                        target = today_violations[idx-1]
                        tid = target['id']
                        print(f"收到删除指令：删除帖子 {tid} (第{idx}个违规帖子)")
                        success = self.poster.delete_thread(self.token, tid)
                        if success:
                            print(f"✅ 已删除帖子 {tid}")
                            self.poster.reply_to_comment(self.token, comment['id'], f"已删除帖子 {tid}")
                        else:
                            print(f"❌ 删除帖子 {tid} 失败")
                            self.poster.reply_to_comment(self.token, comment['id'], f"删除帖子 {tid} 失败，请检查权限")
                    else:
                        self.poster.reply_to_comment(self.token, comment['id'], f"索引 {idx} 超出范围，共有 {len(today_violations)} 个违规帖子")

    # ---------- 主循环 ----------
    def run(self):
        print("[管理员机器人] 启动")
        if not self.login():
            print("登录失败，退出")
            return
        while self.running:
            self.loop_count += 1
            print(f"\n[循环] 第 {self.loop_count} 次执行 - {datetime.now()}")
            scanned, violations = self.scan_threads()
            print(f"[统计] 本次扫描新增记录 {scanned} 个帖子（含评论），发现违规 {violations} 项")
            self.process_admin_commands()
            if self._should_post_report(time.time()):
                self.post_daily_report()
            self._save_state()
            for _ in range(self.scan_interval):
                if not self.running:
                    break
                time.sleep(1)

if __name__ == "__main__":
    import os
    config = {
        "username": os.getenv("BOT_USERNAME"),
        "password": os.getenv("BOT_PASSWORD"),
        "login_retries": 50,
        "target_categories": [2, 5],
    }
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：未设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)
    bot = AdminBot(config, api_key)
    bot.run()
