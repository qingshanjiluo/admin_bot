# admin_bot.py
import time
import os
import json
import signal
import sys
import random
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
        self.admin_category = 15  # 管理板块ID，用于发布日报
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
        self.warned_ids = set()          # 已警告过的帖子ID（包括历史）
        self.daily_log = []               # 每次扫描的日志
        self.daily_violations = []        # 当日新发现的违规（未处理）
        self.processed_violations = []    # 已处理（确认警告）的违规记录，格式：{"thread_id", "title", "type", "reason", "executor", "processed_at", "comment_id"}
        self.loop_count = 0
        self.last_report_time = None
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
                self.daily_log = data.get("daily_log", [])
                self.daily_violations = data.get("daily_violations", [])
                self.processed_violations = data.get("processed_violations", [])
                self.loop_count = data.get("loop_count", 0)
                self.last_report_time = data.get("last_report_time")

    def _save_state(self):
        data = {
            "warned_ids": list(self.warned_ids),
            "daily_log": self.daily_log[-1000:],
            "daily_violations": self.daily_violations[-500:],
            "processed_violations": self.processed_violations,
            "loop_count": self.loop_count,
            "last_report_time": self.last_report_time
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
            return True
        return False

    def check_violation(self, text, comments_text=""):
        """检测违规，结合主帖内容和评论"""
        hit = self._contains_sensitive(text)
        if hit:
            return True, "political", f"命中敏感词: {hit}"
        # 将评论也传递给 AI 进行判断
        full_text = text + "\n\n【评论摘要】\n" + comments_text
        violation, vtype, reason = self.ai.judge_violation(full_text, self.background, self.rules)
        if vtype is None:
            return False, None, "AI调用失败"
        return violation, vtype, reason

    def get_thread_comments_summary(self, thread_id, max_comments=10):
        """获取帖子的前几条评论，返回文本摘要"""
        try:
            comments = self.poster.get_post_comments(self.token, thread_id)
            if not comments:
                return ""
            summary = ""
            for i, c in enumerate(comments[:max_comments]):
                author = c.get('user', {}).get('nickname', '未知')
                content = c.get('content', '')[:100]
                summary += f"评论{i+1} ({author}): {content}\n"
            return summary
        except Exception as e:
            print(f"获取评论摘要失败: {e}")
            return ""

    def scan_threads(self, poster):
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
                threads = poster.get_threads(self.token, cat_id, page_limit=self.max_threads, page_offset=offset)
                if not threads:
                    break
                # 跳过最新的若干条
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
                    # 获取评论摘要
                    comments_summary = self.get_thread_comments_summary(tid)
                    violation, vtype, reason = self.check_violation(full, comments_summary)
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
                        # 检查是否已经在处理记录中（已确认处理）
                        already_processed = any(p['thread_id'] == tid for p in self.processed_violations)
                        if not already_processed:
                            self.daily_violations.append({
                                "time": datetime.now().isoformat(),
                                "thread_id": tid,
                                "title": t['title'],
                                "snippet": snippet,
                                "type": vtype,
                                "reason": reason,
                                "link": f"https://mk48by049.mbbs.cc/#/thread/detail/{tid}"
                            })
                            violations += 1
                            print(f"      ⚠️ 违规！类型: {vtype}, 原因: {reason[:100]}...")
                        else:
                            print(f"      ⚠️ 已处理过，跳过记录")
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

    def process_confirmed_violations(self, poster):
        """扫描管理日报下的评论，处理“确认处理”指令"""
        # 获取管理板块下最近发布的日报（假设标题包含“管理日报”）
        threads = poster.get_threads(self.token, category_id=self.admin_category, page_limit=10)
        for thread in threads:
            if "管理日报" not in thread.get('title', ''):
                continue
            # 获取该日报下的所有评论
            comments = poster.get_post_comments(self.token, thread['id'])
            for comment in comments:
                content = comment.get('content', '')
                # 检查是否包含“确认处理”字样，并提取帖子ID
                import re
                match = re.search(r'确认处理\s*(\d+)', content)
                if match:
                    tid = int(match.group(1))
                    # 检查该帖子是否在 daily_violations 中（未处理）
                    violation = next((v for v in self.daily_violations if v['thread_id'] == tid), None)
                    if not violation:
                        # 可能已经在 processed_violations 中
                        if any(p['thread_id'] == tid for p in self.processed_violations):
                            print(f"帖子 {tid} 已处理过，忽略")
                            continue
                        else:
                            print(f"未找到帖子 {tid} 的违规记录，可能已过期")
                            continue
                    # 执行警告：打开帖子链接，发布警告评论
                    executor = comment.get('user', {}).get('nickname', '未知')
                    warn_content = f"【管理员警告】帖子内容不合规（类型：{violation['type']}），请遵守论坛规则。如有疑问请联系管理员。"
                    success = poster.create_comment(self.token, tid, warn_content)
                    if success:
                        # 记录处理信息
                        processed_record = {
                            "thread_id": tid,
                            "title": violation['title'],
                            "type": violation['type'],
                            "reason": violation['reason'],
                            "executor": executor,
                            "processed_at": datetime.now().isoformat(),
                            "comment_id": comment['id']  # 记录是哪个评论触发的
                        }
                        self.processed_violations.append(processed_record)
                        # 从 daily_violations 中移除
                        self.daily_violations = [v for v in self.daily_violations if v['thread_id'] != tid]
                        print(f"✅ 已处理帖子 {tid}，由 {executor} 确认")
                        # 可选：回复该评论确认处理
                        poster.reply_to_comment(self.token, comment['id'], f"已处理帖子 {tid}，警告已发布。")
                    else:
                        print(f"❌ 发布警告失败，帖子 {tid}")
                    time.sleep(2)

    def _build_report_section(self, violations_sublist, start_idx, total_parts, overall, processed_summary):
        """构建日报的一节，增加处理记录表格"""
        content = f"## 📊 {overall['today']} 违规统计 (第{start_idx}部分/共{total_parts}部分)\n\n"
        content += f"- 今日发现违规帖子：{overall['total_violations']}\n"
        content += f"- 累计审查帖子总数：{overall['total_checked']}\n"
        content += f"- 当前循环次数：{overall['loop_count']}\n\n"
        # 添加历史处理记录表格
        if processed_summary:
            content += "### 📋 已处理违规记录\n"
            content += "| 帖子ID | 标题 | 违规类型 | 执行人 | 处理时间 |\n"
            content += "|-------|------|---------|--------|----------|\n"
            for p in processed_summary:
                title_short = p['title'][:30] + "..." if len(p['title']) > 30 else p['title']
                content += f"| {p['thread_id']} | {title_short} | {p['type']} | {p['executor']} | {p['processed_at'][:16]} |\n"
            content += "\n"
        content += f"### ⚠️ 本部分违规帖子（{len(violations_sublist)}个）\n"
        for idx, v in enumerate(violations_sublist, 1):
            content += f"{idx}. [{v['title']}]({v['link']})\n"
            content += f"   - **类型**：{v['type']}\n"
            content += f"   - **原因**：{v['reason']}\n"
            content += f"   - **原文摘要**：{v.get('snippet', '无')}\n\n"
        content += f"\n---\n*报告由最中幻想天眼管理机器人自动生成*"
        return content

    def post_daily_report(self, poster):
        today = date.today().isoformat()
        # 只包含未处理的违规（即 daily_violations 中的）
        today_violations = self.daily_violations.copy()
        total_violations = len(today_violations)
        total_checked = len(self.warned_ids)

        # 类型分布
        type_dist = {}
        for v in today_violations:
            t = v['type']
            type_dist[t] = type_dist.get(t, 0) + 1

        # 生成总结
        if total_violations > 0:
            summary = self.ai.generate_summary({
                'total_checked': total_checked,
                'total_violations': total_violations,
                'type_distribution': type_dist,
                'loop_count': self.loop_count
            })
        else:
            summary = "今日无违规帖子，大家表现不错！继续加油~ ✨"

        overall_stats = {
            'today': today,
            'total_violations': total_violations,
            'total_checked': total_checked,
            'loop_count': self.loop_count
        }

        # 获取所有历史处理记录（用于表格）
        processed_summary = self.processed_violations[-50:]  # 最近50条

        full_content = self._build_report_section(today_violations, 1, 1, overall_stats, processed_summary)
        if len(full_content) <= 4000:
            full_content += f"\n\n---\n**今日小结**：{summary}\n"
            title = f"【管理日报】{today} 第{self.loop_count}次循环 - 违规 {total_violations} 个"
            success, _ = poster.create_thread(self.token, self.admin_category, title, full_content)
            if success:
                self.last_report_time = time.time()
            return

        # 分片
        print(f"[日报] 内容过长，将拆分为多个帖子发布")
        slices = []
        remaining = today_violations.copy()
        part = 1
        while remaining:
            best = 1
            for cnt in range(1, len(remaining)+1):
                test = self._build_report_section(remaining[:cnt], part, 0, overall_stats, processed_summary)
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
            part_content = self._build_report_section(part_violations, idx, total_parts, overall_stats, processed_summary)
            if idx == total_parts:
                part_content += f"\n\n---\n**今日小结**：{summary}\n"
            part_title = f"【管理日报】{today} 第{self.loop_count}次循环 - 违规 {total_violations} 个（第{idx}部分/共{total_parts}部分）"
            success, _ = poster.create_thread(self.token, self.admin_category, part_title, part_content)
            if success:
                print(f"日报第{idx}部分发布成功")
            else:
                with open(f"failed_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 'w', encoding='utf-8') as f:
                    f.write(f"标题：{part_title}\n\n{part_content}")
            if idx < total_parts:
                time.sleep(self.post_interval_minutes * 60)
        self.last_report_time = time.time()

    def _should_post_report(self, now):
        if self.daily_report_interval == 0:
            return True
        if self.last_report_time is None:
            return True
        return (now - self.last_report_time) >= self.daily_report_interval

    def run(self):
        print("[管理员机器人] 启动")
        if not self.login():
            print("登录失败，退出")
            return
        poster = BBSPoster(self.session, BASE_URL)
        # 将 poster 保存为实例变量，以便其他方法使用
        self.poster = poster
        while self.running:
            self.loop_count += 1
            print(f"\n[循环] 第 {self.loop_count} 次执行 - {datetime.now()}")
            scanned, violations = self.scan_threads(poster)
            # 处理确认指令
            self.process_confirmed_violations(poster)
            print(f"[统计] 新增记录 {scanned} 个帖子，发现违规 {violations} 个")
            if self._should_post_report(time.time()):
                self.post_daily_report(poster)
            self._save_state()
            for _ in range(self.scan_interval):
                if not self.running:
                    break
                time.sleep(1)
