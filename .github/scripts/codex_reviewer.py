#!/usr/bin/env python3
"""
Codex 智能代码审查器
自动审查 Pull Request 并提供改进建议
"""

import os
import sys
import json
import subprocess
from typing import List, Dict, Optional
from github import Github
from openai import OpenAI


class CodexReviewer:
    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        self.openai_api_base = os.environ.get('OPENAI_API_BASE', 'https://api.openai.com/v1')
        self.pr_number = int(os.environ.get('PR_NUMBER', 0))
        self.repository = os.environ.get('REPOSITORY')
        self.comment_body = os.environ.get('COMMENT_BODY', '')
        
        if not all([self.github_token, self.openai_api_key, self.pr_number, self.repository]):
            print("❌ 缺少必要的环境变量")
            sys.exit(1)
        
        self.github = Github(self.github_token)
        self.repo = self.github.get_repo(self.repository)
        self.pr = self.repo.get_pull(self.pr_number)
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.openai_api_key,
            base_url=self.openai_api_base
        )
    
    def get_changed_files(self) -> List[Dict]:
        """获取 PR 中的改动文件"""
        files = []
        for file in self.pr.get_files():
            # 只审查代码文件
            if file.filename.endswith(('.py', '.js', '.ts', '.tsx', '.java', '.go', '.cpp', '.c', '.h')):
                files.append({
                    'filename': file.filename,
                    'status': file.status,
                    'additions': file.additions,
                    'deletions': file.deletions,
                    'changes': file.changes,
                    'patch': file.patch if hasattr(file, 'patch') else None,
                    'blob_url': file.blob_url
                })
        return files
    
    def get_file_content(self, filename: str) -> Optional[str]:
        """获取文件内容"""
        try:
            content = self.repo.get_contents(filename, ref=self.pr.head.sha)
            return content.decoded_content.decode('utf-8')
        except:
            return None
    
    def analyze_with_codex(self, file_info: Dict) -> Optional[Dict]:
        """使用 Codex (GPT-4) 分析代码"""
        filename = file_info['filename']
        patch = file_info.get('patch', '')
        
        if not patch:
            return None
        
        # 获取完整文件内容以提供上下文
        full_content = self.get_file_content(filename)
        
        # 构建针对缠论量化系统的审查提示
        system_prompt = """你是一位资深的代码审查专家，专精于：
1. 缠论量化交易系统（笔、线段、中枢、买卖点识别）
2. Python 最佳实践和性能优化
3. 交易策略的风险控制
4. 代码安全性和可维护性

请审查代码变更，重点关注：
- 算法逻辑的正确性
- 潜在的 bug 或边界情况
- 性能优化机会
- 代码风格和可读性
- 安全隐患

如果代码质量很好，只需回复 "👍 代码看起来不错"。
如果有改进建议，请给出具体的、可操作的建议，并标注行号。
用中文简体回复。"""

        user_prompt = f"""文件: {filename}
状态: {file_info['status']}
改动: +{file_info['additions']} -{file_info['deletions']}

代码变更:
```diff
{patch}
```
"""

        if full_content and len(full_content) < 10000:  # 限制文件大小
            user_prompt += f"\n完整文件内容（供参考）:\n```python\n{full_content[:5000]}\n```"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",  # 使用 GPT-4，具有强大的代码理解能力
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # 较低的温度使输出更确定
                max_tokens=1000
            )
            
            review_text = response.choices[0].message.content.strip()
            
            # 判断是否只是简单的通过
            is_approval = "👍" in review_text and len(review_text) < 50
            
            return {
                'filename': filename,
                'review': review_text,
                'is_approval': is_approval
            }
        
        except Exception as e:
            print(f"❌ 分析 {filename} 时出错: {e}")
            return None
    
    def post_review_comment(self, reviews: List[Dict]):
        """发布审查评论到 PR"""
        if not reviews:
            print("ℹ️ 没有需要发布的审查意见")
            return
        
        # 统计审查结果
        approvals = [r for r in reviews if r.get('is_approval')]
        suggestions = [r for r in reviews if not r.get('is_approval')]
        
        # 构建评论内容
        comment_parts = ["## 🤖 Codex 代码审查\n"]
        
        if approvals:
            comment_parts.append(f"### ✅ 通过审查 ({len(approvals)} 个文件)\n")
            for review in approvals:
                comment_parts.append(f"- `{review['filename']}` - {review['review']}\n")
            comment_parts.append("\n")
        
        if suggestions:
            comment_parts.append(f"### 💡 改进建议 ({len(suggestions)} 个文件)\n")
            for review in suggestions:
                comment_parts.append(f"#### 📄 `{review['filename']}`\n")
                comment_parts.append(f"{review['review']}\n\n")
        
        # 添加底部说明
        comment_parts.append("---\n")
        comment_parts.append("_💡 提示: 在评论中提及 `@codex` 可以请求重新审查或提问_")
        
        comment_body = "".join(comment_parts)
        
        # 发布评论
        try:
            self.pr.create_issue_comment(comment_body)
            print(f"✅ 已发布审查意见到 PR #{self.pr_number}")
        except Exception as e:
            print(f"❌ 发布评论失败: {e}")
    
    def handle_mention(self):
        """处理 @codex 提及"""
        if '@codex' not in self.comment_body:
            return False
        
        # 提取用户的问题或请求
        comment_text = self.comment_body.replace('@codex', '').strip()
        
        if not comment_text:
            # 如果只是提及 @codex，触发完整审查
            return True
        
        # 使用 GPT-4 回答用户的问题
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "你是一位代码审查助手，专精于缠论量化交易系统。请用中文简体回复用户的问题。"
                    },
                    {
                        "role": "user", 
                        "content": f"关于这个 Pull Request，用户问: {comment_text}"
                    }
                ],
                temperature=0.5,
                max_tokens=500
            )
            
            answer = response.choices[0].message.content.strip()
            
            # 回复用户
            reply = f"## 🤖 Codex 回复\n\n{answer}"
            
            # 如果是对评论的回复
            if os.environ.get('COMMENT_ID'):
                # 在 PR 评论中回复
                self.pr.create_issue_comment(reply)
            else:
                self.pr.create_issue_comment(reply)
            
            print(f"✅ 已回复 @codex 提及")
            return False  # 不需要完整审查
        
        except Exception as e:
            print(f"❌ 回复提及失败: {e}")
            return True  # 失败时执行完整审查
    
    def run(self):
        """运行审查流程"""
        print(f"🔍 开始审查 PR #{self.pr_number}: {self.pr.title}")
        
        # 检查是否是 @codex 提及
        if self.comment_body:
            should_review = self.handle_mention()
            if not should_review:
                return
        
        # 获取改动文件
        changed_files = self.get_changed_files()
        print(f"📝 发现 {len(changed_files)} 个代码文件改动")
        
        if not changed_files:
            print("ℹ️ 没有需要审查的代码文件")
            return
        
        # 对每个文件进行审查
        reviews = []
        for file_info in changed_files:
            print(f"🔎 正在分析: {file_info['filename']}")
            review = self.analyze_with_codex(file_info)
            if review:
                reviews.append(review)
        
        # 发布审查意见
        if reviews:
            self.post_review_comment(reviews)
            print(f"✅ 审查完成! 共审查 {len(reviews)} 个文件")
        else:
            print("ℹ️ 没有生成审查意见")


if __name__ == '__main__':
    try:
        reviewer = CodexReviewer()
        reviewer.run()
    except Exception as e:
        print(f"❌ 审查过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

