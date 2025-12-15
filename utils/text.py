# -*- coding: utf-8 -*-
"""
文本处理工具
提供清洗、截断、JSON 提取等功能
"""

import re
import json
import logging
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)


def clean_text(
    text: str,
    remove_html: bool = True,
    remove_urls: bool = False,
    remove_extra_whitespace: bool = True,
    max_length: Optional[int] = None
) -> str:
    """
    清洗文本
    
    Args:
        text: 原始文本
        remove_html: 是否移除 HTML 标签
        remove_urls: 是否移除 URL
        remove_extra_whitespace: 是否压缩多余空白
        max_length: 最大长度（可选）
        
    Returns:
        清洗后的文本
    """
    if not text:
        return ""
    
    text = str(text)
    
    # 移除 HTML 标签
    if remove_html:
        text = re.sub(r'<[^>]+>', '', text)
    
    # 移除 URL
    if remove_urls:
        text = re.sub(r'https?://\S+', '', text)
    
    # 压缩多余空白
    if remove_extra_whitespace:
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
    
    # 截断
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def truncate_text(
    text: str,
    max_length: int,
    suffix: str = "...",
    word_boundary: bool = False
) -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 原始文本
        max_length: 最大长度（包含后缀）
        suffix: 截断后缀
        word_boundary: 是否在单词边界截断（英文）
        
    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_length:
        return text or ""
    
    # 计算实际可用长度
    target_len = max_length - len(suffix)
    if target_len <= 0:
        return suffix[:max_length]
    
    truncated = text[:target_len]
    
    # 在单词边界截断
    if word_boundary:
        last_space = truncated.rfind(' ')
        if last_space > target_len * 0.5:  # 至少保留 50% 的内容
            truncated = truncated[:last_space]
    
    return truncated + suffix


def extract_json_from_text(text: str) -> Optional[Union[Dict, list]]:
    """
    从文本中提取 JSON
    
    支持：
    - 纯 JSON 文本
    - ```json ... ``` 代码块
    - 混合文本中的 JSON
    
    Args:
        text: 可能包含 JSON 的文本
        
    Returns:
        解析后的 JSON 对象，失败返回 None
    """
    if not text:
        return None
    
    text = text.strip()
    
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 移除代码块标记
    if "```" in text:
        # 移除开头的 ```json 或 ```
        text_clean = re.sub(r'^\s*```(?:json)?\s*', '', text, flags=re.I)
        # 移除结尾的 ```
        text_clean = re.sub(r'\s*```\s*$', '', text_clean)
        try:
            return json.loads(text_clean)
        except json.JSONDecodeError:
            text = text_clean  # 继续使用清理后的文本
    
    # 查找 { } 边界
    i, j = text.find("{"), text.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(text[i:j+1])
        except json.JSONDecodeError:
            pass
    
    # 查找 [ ] 边界（数组）
    i, j = text.find("["), text.rfind("]")
    if 0 <= i < j:
        try:
            return json.loads(text[i:j+1])
        except json.JSONDecodeError:
            pass
    
    return None


def normalize_whitespace(text: str) -> str:
    """
    标准化空白字符
    
    - 将多个空格/制表符压缩为单个空格
    - 将多个换行压缩为单个换行
    - 移除首尾空白
    """
    if not text:
        return ""
    
    # 将制表符和多个空格替换为单个空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 将多个换行替换为单个换行
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # 移除每行首尾空格
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def remove_markdown(text: str) -> str:
    """
    移除 Markdown 格式标记
    
    移除：标题、粗体、斜体、链接、代码块等
    """
    if not text:
        return ""
    
    # 移除代码块
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    
    # 移除标题标记
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # 移除粗体/斜体
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # 移除链接，保留文字
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # 移除图片
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
    
    # 移除水平线
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # 移除列表标记
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    return normalize_whitespace(text)


def safe_json_dumps(obj: Any, ensure_ascii: bool = False, **kwargs) -> str:
    """
    安全的 JSON 序列化
    
    处理无法序列化的类型（datetime、bytes 等）
    """
    def default_handler(o):
        if hasattr(o, 'isoformat'):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.decode('utf-8', errors='replace')
        if hasattr(o, '__dict__'):
            return o.__dict__
        return str(o)
    
    return json.dumps(obj, ensure_ascii=ensure_ascii, default=default_handler, **kwargs)


def extract_keywords(text: str, max_keywords: int = 10) -> list:
    """
    简单的关键词提取（基于词频）
    
    Args:
        text: 输入文本
        max_keywords: 最大关键词数
        
    Returns:
        关键词列表
    """
    if not text:
        return []
    
    # 中文分词（简单按字符和空格分割）
    # 如需更精确的分词，可以引入 jieba
    words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text.lower())
    
    # 过滤短词
    words = [w for w in words if len(w) >= 2]
    
    # 统计词频
    from collections import Counter
    word_counts = Counter(words)
    
    # 返回最高频词
    return [word for word, _ in word_counts.most_common(max_keywords)]
