# deepseek_client.py
import requests
import json
import os

class DeepSeekClient:
    def __init__(self, api_key=None, base_url="https://api.deepseek.com/v1"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY")
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })

    def generate(self, prompt, max_tokens=200, temperature=0.8, model="deepseek-chat"):
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                print(f"DeepSeek API 错误: {response.status_code}")
                return ""
        except Exception as e:
            print(f"DeepSeek API 异常: {e}")
            return ""

    def generate_summary(self, data):
        """生成日报摘要（可选）"""
        prompt = f"请根据以下统计数据生成一段简洁的日报小结：{json.dumps(data, ensure_ascii=False)}"
        return self.generate(prompt, max_tokens=100, temperature=0.7)

    def judge_violation(self, text, background, rules):
        """判断违规（用于管理员机器人）"""
        prompt = f"""
请判断以下帖子内容是否违规。违规类型包括：政治敏感、色情、暴力、人身攻击、广告等。背景知识：{background}。规则：{rules}
内容：{text}
输出格式：{{"violation": true/false, "type": "类型", "reason": "理由"}}
"""
        response = self.generate(prompt, max_tokens=100, temperature=0.3)
        try:
            result = json.loads(response)
            return result.get("violation", False), result.get("type"), result.get("reason")
        except:
            return False, None, None
