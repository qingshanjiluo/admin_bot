# post.py
import requests
import json

class BBSPoster:
    def __init__(self, session, base_url):
        self.session = session
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/bbs"
        # 添加必需的 mbbs-domain 头（所有请求自动携带）
        self.session.headers.update({
            'mbbs-domain': 'mk48by049.mbbs.cc'
        })
        self.user_id = None   # 登录后设置

        # API 端点
        self.create_thread_url = f"{self.api_base}/threads/create"
        self.list_threads_url = f"{self.api_base}/threads/list"
        self.thread_url = f"{self.api_base}/threads"
        self.list_posts_url = f"{self.api_base}/posts/list"
        self.create_post_url = f"{self.api_base}/posts/create"
        self.set_essence_url = f"{self.api_base}/threads/setEssence"
        self.set_sticky_url = f"{self.api_base}/threads/setSticky"
        self.set_approved_url = f"{self.api_base}/threads/setApproved"
        self.set_thread_like_url = f"{self.api_base}/threads/setLike"
        self.set_post_like_url = f"{self.api_base}/posts/setLike"
        self.batch_delete_threads_url = f"{self.api_base}/threads/batchDelete"
        self.batch_delete_posts_url = f"{self.api_base}/posts/batchDeletePosts"
        self.create_comment_reply_url = f"{self.api_base}/posts/createComment"
        self.list_comments_replies_url = f"{self.api_base}/posts/listComments"
        self.user_list_url = f"{self.api_base}/users/list"

    # ---------- 发帖 ----------
    def create_thread(self, token, category_id, title, content):
        try:
            headers = {'Authorization': token, 'Content-Type': 'application/json'}
            data = {"category_id": category_id, "title": title, "content": content}
            r = self.session.post(self.create_thread_url, json=data, headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    return True, res.get('data', {})
            print(f"发帖失败: {r.text[:200]}")
            return False, None
        except Exception as e:
            print(f"发帖异常: {e}")
            return False, None

    # ---------- 获取帖子列表 ----------
    def get_threads(self, token, category_id=None, page_limit=20, page_offset=0, user_id=None):
        headers = {'Authorization': token}
        params = {"page_limit": page_limit, "page_offset": page_offset, "sort": "-created_at"}
        if category_id:
            params["category_id"] = category_id
        if user_id:
            params["user_id"] = user_id
        try:
            r = self.session.get(self.list_threads_url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    return res.get('data', [])
        except Exception as e:
            print(f"获取帖子列表异常: {e}")
        return []

    # ---------- 获取帖子详情 ----------
    def get_thread_detail(self, token, thread_id):
        headers = {'Authorization': token}
        try:
            r = self.session.get(f"{self.thread_url}/{thread_id}", headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    return res.get('data')
        except Exception as e:
            print(f"获取帖子详情异常: {e}")
        return None

    # ---------- 获取一级评论 ----------
    def get_post_comments(self, token, thread_id):
        headers = {'Authorization': token}
        params = {"thread_id": thread_id, "page_limit": 200, "page_offset": 0}
        try:
            r = self.session.get(self.list_posts_url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    posts = res.get('data', [])
                    return [p for p in posts if not p.get('is_first', True)]
        except Exception as e:
            print(f"获取评论异常: {e}")
        return []

    # ---------- 获取嵌套回复 ----------
    def get_comment_replies(self, token, post_id, page_limit=100, page_offset=0):
        headers = {'Authorization': token}
        params = {"post_id": post_id, "page_limit": page_limit, "page_offset": page_offset}
        try:
            r = self.session.get(self.list_comments_replies_url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    data = res.get('data', {})
                    if isinstance(data, list):
                        return data
                    else:
                        return data.get('list', [])
        except Exception as e:
            print(f"获取嵌套回复异常: {e}")
        return []

    # ---------- 发布一级评论 ----------
    def create_comment(self, token, thread_id, content):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_id": thread_id, "content": content}
        try:
            r = self.session.post(self.create_post_url, json=data, headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    print(f"✅ 评论发布成功，帖子 {thread_id}")
                    return True
            print(f"❌ 评论失败: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"评论异常: {e}")
            return False

    # ---------- 回复评论（嵌套）----------
    def reply_to_comment(self, token, post_id, content, comment_post_id=None):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"post_id": post_id, "content": content}
        if comment_post_id:
            data["comment_post_id"] = comment_post_id
        try:
            r = self.session.post(self.create_comment_reply_url, json=data, headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    print(f"✅ 嵌套回复成功，评论 {post_id}")
                    return True
            print(f"❌ 嵌套回复失败: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"嵌套回复异常: {e}")
            return False

    # ---------- 删除帖子（需要管理员权限）----------
    def delete_thread(self, token, thread_id):
        headers = {
            'Authorization': token,
            'mbbs-domain': 'mk48by049.mbbs.cc',
            'mbbs-userid': str(self.user_id) if self.user_id else ''
        }
        try:
            r = self.session.delete(f"{self.thread_url}/{thread_id}", headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                return res.get('success', False)
            print(f"删除失败: HTTP {r.status_code}")
            return False
        except Exception as e:
            print(f"删除帖子异常: {e}")
            return False

    # ---------- 删除评论 ----------
    def delete_comment(self, token, comment_id):
        headers = {'Authorization': token}
        try:
            r = self.session.delete(f"{self.api_base}/posts/{comment_id}", headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"删除评论异常: {e}")
            return False

    # ---------- 设置精华 ----------
    def set_essence(self, token, thread_id, is_essence=True):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_id": thread_id, "is_essence": is_essence}
        try:
            r = self.session.post(self.set_essence_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"设置精华异常: {e}")
            return False

    # ---------- 设置置顶 ----------
    def set_sticky(self, token, thread_id, is_sticky=True):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_id": thread_id, "is_sticky": is_sticky}
        try:
            r = self.session.post(self.set_sticky_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"设置置顶异常: {e}")
            return False

    # ---------- 审核帖子 ----------
    def set_approved(self, token, thread_id, is_approved=True):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_id": thread_id, "is_approved": is_approved}
        try:
            r = self.session.post(self.set_approved_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"审核帖子异常: {e}")
            return False

    # ---------- 点赞帖子 ----------
    def set_thread_like(self, token, thread_id, like=True):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_id": thread_id, "is_like": like}
        try:
            r = self.session.post(self.set_thread_like_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"点赞帖子异常: {e}")
            return False

    # ---------- 点赞评论 ----------
    def set_post_like(self, token, post_id, like=True):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"post_id": post_id, "is_like": like}
        try:
            r = self.session.post(self.set_post_like_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"点赞评论异常: {e}")
            return False

    # ---------- 批量删除帖子 ----------
    def batch_delete_threads(self, token, thread_ids):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"thread_ids": thread_ids}
        try:
            r = self.session.post(self.batch_delete_threads_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"批量删除帖子异常: {e}")
            return False

    # ---------- 批量删除评论 ----------
    def batch_delete_comments(self, token, comment_ids):
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        data = {"post_ids": comment_ids}
        try:
            r = self.session.post(self.batch_delete_posts_url, json=data, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception as e:
            print(f"批量删除评论异常: {e}")
            return False

    # ---------- 获取用户列表（管理员）----------
    def get_user_list(self, token, page=1, page_size=20, search=""):
        headers = {'Authorization': token}
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        try:
            r = self.session.get(self.user_list_url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    return res.get('data', [])
        except Exception as e:
            print(f"获取用户列表异常: {e}")
        return []

    # ---------- 获取未读消息数量 ----------
    def get_unread_message_count(self, token, user_id):
        url = f"{self.api_base}/message/unreadMessageCount"
        headers = {'Authorization': token, 'mbbs-userid': str(user_id)}
        try:
            r = self.session.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get('success'):
                    return res.get('data', 0)
        except Exception as e:
            print(f"获取未读消息异常: {e}")
        return 0
