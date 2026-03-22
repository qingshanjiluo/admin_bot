# login.py
import requests
import json
import time
import re

class BBSTurkeyBotLogin:
    def __init__(self, base_url, username, password, max_retries=50):
        self.base_url = base_url
        self.api_base = f"{base_url}/bbs"
        self.username = username
        self.password = password
        self.max_login_attempts = max_retries
        self.max_captcha_retries = 3
        self.session = requests.Session()
        self._setup_headers()
        self.ocr = self._init_ddddocr()

    def _setup_headers(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Termux) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/login',
            'Content-Type': 'application/json'
        })

    def _init_ddddocr(self):
        try:
            import ddddocr
            print("[OK] ddddocr 初始化成功")
            return ddddocr.DdddOcr(show_ad=False)
        except ImportError:
            print("[错误] ddddocr 未安装")
            return None
        except Exception as e:
            print(f"[错误] ddddocr 初始化失败: {e}")
            return None

    def svg_to_png_cairosvg(self, svg_content: str) -> bytes:
        try:
            import cairosvg
            return cairosvg.svg2png(
                bytestring=svg_content.encode('utf-8'),
                output_width=300,
                output_height=100,
                dpi=200
            )
        except ImportError:
            print("[错误] cairosvg 未安装")
            return None
        except Exception as e:
            print(f"[错误] cairosvg 转换失败: {e}")
            return None

    def get_login_captcha(self):
        try:
            print("[相机] 获取登录验证码...")
            response = self.session.get(f"{self.api_base}/login/captcha", timeout=10)
            if response.status_code == 200:
                data = response.json()
                captcha_data = data.get('data', {})
                captcha_id = captcha_data.get('id')
                svg_data = captcha_data.get('svg')
                if captcha_id and svg_data:
                    print(f"[OK] 验证码获取成功, ID: {captcha_id}")
                    return captcha_id, svg_data
            print("[错误] 验证码获取失败")
            return None, None
        except Exception as e:
            print(f"[错误] 获取验证码错误: {e}")
            return None, None

    def recognize_captcha_with_retry(self, svg_data: str) -> str:
        if not self.ocr:
            print("[错误] ddddocr 未初始化")
            return None
        for attempt in range(self.max_captcha_retries):
            try:
                print(f"[识别] 第 {attempt + 1} 次尝试识别验证码...")
                png_data = self.svg_to_png_cairosvg(svg_data)
                if not png_data:
                    continue
                result = self.ocr.classification(png_data)
                cleaned = re.sub(r'[^A-Za-z0-9]', '', result).upper()
                if cleaned:
                    print(f"[OK] 验证码识别成功: {cleaned}")
                    return cleaned
                else:
                    print(f"[警告] 验证码识别结果为空，重新识别...")
            except Exception as e:
                print(f"[错误] 验证码识别失败: {e}")
            if attempt < self.max_captcha_retries - 1:
                time.sleep(1)
        print("[错误] 验证码识别重试次数用尽")
        return None

    def login_with_captcha(self, captcha_id: str, captcha_text: str) -> tuple:
        try:
            login_data = {
                "username": self.username,
                "password": self.password,
                "captcha_id": captcha_id,
                "captcha_text": captcha_text
            }
            print("[登录] 提交登录请求...")
            response = self.session.post(f"{self.api_base}/login", json=login_data, timeout=15)
            print(f"[响应] 状态码: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"[登录] 响应: {json.dumps(result, ensure_ascii=False)}")
                if result.get('success') is True:
                    user_data = result.get('data', {})
                    if user_data and ('id' in user_data or 'token' in user_data):
                        print("[成功] 登录成功!")
                        return True, result, None
                    else:
                        error_msg = "响应数据不完整"
                        print(f"[错误] 登录失败: {error_msg}")
                        return False, None, error_msg
                else:
                    error_msg = result.get('message', '未知错误')
                    print(f"[错误] 登录失败: {error_msg}")
                    return False, None, error_msg
            else:
                print(f"[错误] HTTP 错误: {response.status_code}")
                return False, None, f"HTTP {response.status_code}"
        except Exception as e:
            print(f"[错误] 登录请求异常: {e}")
            return False, None, str(e)

    def login_with_retry(self):
        print("[启动] 开始登录流程...")
        print(f"[账号] 用户名: {self.username}")
        print(f"[设置] 最大重试次数: {self.max_login_attempts}")
        print("=" * 50)
        login_attempts = 0
        while login_attempts < self.max_login_attempts:
            login_attempts += 1
            print(f"\n[尝试] 第 {login_attempts}/{self.max_login_attempts} 次登录尝试...")
            captcha_id, svg_data = self.get_login_captcha()
            if not captcha_id:
                print("[错误] 获取验证码失败，继续重试...")
                time.sleep(2)
                continue
            captcha_text = self.recognize_captcha_with_retry(svg_data)
            if not captcha_text:
                print("[错误] 验证码识别失败，继续重试...")
                time.sleep(2)
                continue
            success, result, error_msg = self.login_with_captcha(captcha_id, captcha_text)
            if success:
                print(f"[成功] 登录成功！总共尝试 {login_attempts} 次")
                return True, result, self.session
            if error_msg and ("验证码" in error_msg or "captcha" in error_msg.lower()):
                print("[重试] 验证码错误，立即重试...")
                continue
            else:
                print("[等待] 其他错误，等待 2 秒后重试...")
                time.sleep(2)
        print(f"[失败] 登录失败！已达到最大重试次数 {self.max_login_attempts}")
        return False, None, None
