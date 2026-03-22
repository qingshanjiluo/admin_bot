# post.py
import requests
import json

class BBSPoster:
    def __init__(self, session, base_url):
        self.session = session
        self.base_url = base_url
        self.api_base = f"{base_url}/bbs"
        self.create_thread_url = f"{self.api_base}/threads/create"
        self.list_threads_url = f"{self.api_base}/threads/list"
        self.list_posts_url = f"{self.api_base}/posts/list"
        self.create_post_url = f"{self.api_base}/posts/create"

    def create_thread(self, token, category_id, title, content):
        try:
            headers = {'Authorization': token, 'Content-Type': 'application/json'}
            thread_data = {
                "category_id": category_id,
                "title": title,
                "content": content
            }
            print(f"[发帖] 创建帖子: {title}")
            response = self.session.post(self.create_thread_url, json=thread_data, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('success') is True:
                    thread_data = result.get('data', {})
                    if 'id' in thread_data:
                        print(f"[成功] 发帖成功！帖子ID: {thread_data.get('id')}")
                        return True, thread_data
                print(f"[失败] 发帖失败: {result.get('message', '未知错误')}")
                return False, None
            else:
                print(f"[错误] 发帖HTTP错误: {response.status_code}")
                return False, None
        except Exception as e:
            print(f"[异常] 发帖异常: {e}")
            return False, None

    def get_threads(self, token, category_id=None, page_limit=20, page_offset=0, user_id=None):
        try:
            headers = {'Authorization': token}
            params = {
                "page_limit": page_limit,
                "page_offset": page_offset,
                "sort": "-created_at"
            }
            if category_id:
                params["category_id"] = category_id
            if user_id:
                params["user_id"] = user_id
            response = self.session.get(self.list_threads_url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('success') is True:
                    threads = result.get('data', [])
                    print(f"[信息] 获取到 {len(threads)} 个帖子 (页偏移 {page_offset})")
                    return threads
                else:
                    print(f"[失败] 获取帖子列表失败: {result.get('message')}")
                    return []
            else:
                print(f"[错误] 获取帖子列表HTTP错误: {response.status_code}")
                return []
        except Exception as e:
            print(f"[异常] 获取帖子列表异常: {e}")
            return []

    def get_post_comments(self, token, thread_id):
        try:
            headers = {'Authorization': token}
            params = {"thread_id": thread_id, "page_limit": 200, "page_offset": 0}
            response = self.session.get(self.list_posts_url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('success') is True:
                    posts = result.get('data', [])
                    comments = [post for post in posts if not post.get('is_first', True)]
                    return comments
                else:
                    print(f"[失败] 获取评论失败: {result.get('message')}")
                    return []
            else:
                print(f"[错误] 获取评论HTTP错误: {response.status_code}")
                return []
        except Exception as e:
            print(f"[异常] 获取评论异常: {e}")
            return []

    def create_comment(self, token, thread_id, content):
        try:
            headers = {'Authorization': token, 'Content-Type': 'application/json'}
            post_data = {"thread_id": thread_id, "content": content}
            response = self.session.post(self.create_post_url, json=post_data, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('success') is True:
                    print(f"[成功] 评论发布成功！帖子ID: {thread_id}")
                    return True
                else:
                    print(f"[失败] 评论发布失败: {result.get('message')}")
                    return False
            else:
                print(f"[错误] 评论发布HTTP错误: {response.status_code}")
                return False
        except Exception as e:
            print(f"[异常] 评论发布异常: {e}")
            return False
