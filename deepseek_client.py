# deepseek_client.py
import requests
import json
import random

class DeepSeekClient:
    def __init__(self, api_key, model="deepseek-chat", base_url="https://api.deepseek.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        print(f"[DeepSeek] 客户端初始化成功，模型: {self.model}")

    def _call_api(self, messages, temperature=0.3, max_tokens=200):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                print(f"[DeepSeek] HTTP错误: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"[DeepSeek] 调用异常: {e}")
            return None

    def judge_violation(self, content, background=None, rules=None):
        prompt = f"""
你是一个论坛内容审核助手。以下信息供参考：

【游戏背景】
{background[:1000] if background else "无"}

【论坛核心规则】
{rules[:1500] if rules else "无"}

请判断下面帖子内容是否违规。只有明显违反规则（政治敏感、色情、暴力、开盒、恶意刷屏等）才判定为违规。正常的游戏讨论、教程、生活分享、舰队广告、闲聊等均不违规。

帖子内容：
{content}

请输出JSON：{{"violation": true/false, "type": "类型", "reason": "详细说明，可引用规则条款"}}
类型：political, porn, violence, discrimination, privacy, ad, nonsense, default
"""
        messages = [{"role": "user", "content": prompt}]
        result = self._call_api(messages, temperature=0.3, max_tokens=300)
        if result:
            try:
                import re
                result = result.strip()
                match = re.search(r'\{.*\}', result, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    violation = data.get('violation', False)
                    vtype = data.get('type', 'default')
                    reason = data.get('reason', '')
                    return violation, vtype, reason
            except Exception as e:
                print(f"[DeepSeek] JSON解析失败: {e}")
        return False, None, ""

    def generate_summary(self, stats):
        prompt = f"""你是一个论坛管理机器人，刚刚完成了第{stats['loop_count']}轮扫描。本次共检查了{stats['total_scanned']}个帖子，发现{stats['total_violations']}个违规。累计已审查{stats['total_checked']}个帖子。请用活泼可爱的语气（可以使用颜文字）写一段简短的今日工作总结，长度在2-3句话，鼓励大家遵守规则，营造良好社区氛围。"""
        messages = [{"role": "user", "content": prompt}]
        result = self._call_api(messages, temperature=0.7, max_tokens=150)
        if result:
            return result.strip()
        else:
            return "大家今天表现不错，继续加油哦！(｡•̀ᴗ-)✧"
