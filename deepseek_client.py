# deepseek_client.py
import requests
import json
import os

class DeepSeekClient:
    """
    OpenAI 兼容 API 客户端（支持 DeepSeek、OpenAI 等）
    用于违规判断和生成可爱风格的警告消息。
    """

    def __init__(self, api_key=None, base_url=None):
        """
        初始化 API 客户端
        :param api_key: API 密钥，默认从环境变量 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 读取
        :param base_url: API 基础地址，默认从环境变量 OPENAI_BASE_URL 或 DEEPSEEK_BASE_URL 读取，若未设置则使用 DeepSeek 官方地址
        """
        # 读取 API Key（优先级：参数 > OPENAI_API_KEY > DEEPSEEK_API_KEY）
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置环境变量 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")

        # 读取 Base URL（优先级：参数 > OPENAI_BASE_URL > DEEPSEEK_BASE_URL > 默认）
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
        if not self.base_url:
            self.base_url = "https://api.deepseek.com/v1"
        self.base_url = self.base_url.rstrip('/')

        # 读取模型名称（优先级：环境变量 OPENAI_MODEL > DEEPSEEK_MODEL > 默认）
        self.model = os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        # 注意：如果您的 DeepSeek 账号需要特定模型（如 deepseek-v4-pro），请设置环境变量 DEEPSEEK_MODEL

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })
        print(f"✅ API 客户端初始化成功，Base URL: {self.base_url}, Model: {self.model}")

    def generate(self, prompt, max_tokens=200, temperature=0.8, model=None):
        """
        生成文本
        :param prompt: 用户提示词
        :param max_tokens: 最大生成 token 数
        :param temperature: 随机性 (0-1)
        :param model: 模型名称，若不传则使用 self.model
        :return: 生成的文本字符串
        """
        model = model or self.model
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
                print(f"API 请求失败: {response.status_code} - {response.text}")
                return ""
        except Exception as e:
            print(f"API 调用异常: {e}")
            return ""

    def generate_summary(self, data):
        """
        生成日报摘要（用于管理员机器人）
        :param data: 统计数据字典
        :return: 摘要文本
        """
        prompt = f"请根据以下统计数据生成一段简洁的日报小结（不超过100字，专业语气）：{json.dumps(data, ensure_ascii=False)}"
        return self.generate(prompt, max_tokens=100, temperature=0.7)

    def judge_violation(self, text, context_text="", background="", rules=""):
        """
        判断帖子/评论是否违规（用于管理员机器人）
        :param text: 待检测文本
        :param context_text: 上下文（例如整个帖子的其他评论或主贴内容）
        :param background: 背景知识（如 mk48.txt）
        :param rules: 规则文本（如 rules.txt）
        :return: (is_violation, violation_type, reason)
        """
        full_text = text
        if context_text:
            full_text = f"【待检测内容】\n{text}\n\n【上下文（同一帖子的其他内容，仅供参考）】\n{context_text}"
        prompt = f"""
请判断以下内容是否违反论坛规则。**务必结合上下文理解**，避免断章取义。

违规类型：
- political: 政治敏感（键政、领导人、敏感事件）
- porn: 色情低俗、性暗示
- violence: 暴力血腥、恐怖主义
- discrimination: 种族/性别/宗教歧视
- privacy: 泄露他人隐私（开盒）
- ad: 商业广告（正常游戏交流、教程不视为违规）
- default: 正常内容

**重要**：
- 网络口语（如"zzz"表示睡觉、"hhh"、"qwq"、"草"等）不视为违规。
- 正常游戏讨论、吐槽、闲聊不违规。
- 只有明显恶意攻击、辱骂、涉政、涉黄才判违规。

背景知识：{background}
规则：{rules}

{full_text}

输出格式：{{"violation": true/false, "type": "类型", "reason": "简短理由（15字以内）"}}
"""
        response = self.generate(prompt, max_tokens=80, temperature=0.3)
        try:
            result = json.loads(response)
            violation = result.get("violation", False)
            vtype = result.get("type", "default")
            reason = result.get("reason", "")
            # 如果类型是 default，强制将违规标志设为 False
            if vtype == "default":
                violation = False
            allowed_types = {'political','porn','violence','discrimination','privacy','ad','default'}
            if vtype not in allowed_types:
                vtype = 'default'
                violation = False
            return violation, vtype, reason
        except Exception as e:
            print(f"违规判断 JSON 解析失败: {e}")
            return False, None, ""

    def generate_warning(self, violation_type, reason, target_type="帖子"):
        """
        生成可爱风格的警告消息（完整文本由 AI 生成）
        :param violation_type: 违规类型（political, porn, violence 等）
        :param reason: AI 判断出的简短原因
        :param target_type: "帖子" 或 "评论"
        :return: 完整的警告文本（不超过 60 字）
        """
        prompt = f"""
你是一个可爱的猫娘论坛管理员。请根据以下信息生成一条简短的警告消息（不超过 60 字），语气要萌、带颜文字（如 ⊙∀⊙、喵~、qwq 等），提醒用户遵守版规。

违规类型：{violation_type}
违规原因：{reason}
违规对象：{target_type}

输出格式：直接输出警告文本，不要加引号或额外说明。
"""
        return self.generate(prompt, max_tokens=80, temperature=0.7)
