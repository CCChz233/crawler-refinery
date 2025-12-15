# -*- coding: utf-8 -*-
"""
LLM 调用封装
支持火山引擎 Volcano API（OpenAI 兼容格式）
"""

import json
import time
import logging
import requests
from typing import Dict, Any, Optional, Union, List

from config_loader import config

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM 客户端，封装火山引擎 API 调用
    
    用法：
        client = LLMClient()
        response = client.chat("你好")
        json_response = client.chat_json("返回一个JSON", schema={"name": "string"})
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        self.api_key = api_key or config.volcano_api_key
        self.base_url = (base_url or config.volcano_base_url).rstrip('/')
        self.model = model or config.volcano_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    def chat(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        """
        调用 LLM 进行对话
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            temperature: 温度参数
            max_tokens: 最大返回 token 数
            
        Returns:
            LLM 响应文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        url = f"{self.base_url}/chat/completions"
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content.strip()
            
            except requests.exceptions.Timeout:
                logger.warning(f"LLM 请求超时 (尝试 {attempt + 1}/{self.max_retries + 1})")
            except requests.exceptions.RequestException as e:
                logger.warning(f"LLM 请求失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.warning(f"LLM 响应解析失败: {e}")
                return ""
            
            if attempt < self.max_retries:
                time.sleep(self.retry_delay * (attempt + 1))
        
        logger.error(f"LLM 请求失败，已重试 {self.max_retries} 次")
        return ""
    
    def chat_json(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        schema: Optional[Dict] = None,
        temperature: float = 0.1,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 并解析 JSON 响应
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示（可选）
            schema: 期望的 JSON 结构说明（可选，会追加到 prompt）
            temperature: 温度参数（JSON 场景建议低温）
            
        Returns:
            解析后的 JSON 字典，失败返回 None
        """
        # 如果有 schema，追加到 prompt
        if schema:
            schema_hint = f"\n\n请严格按照以下 JSON 格式返回：\n```json\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n```"
            prompt = prompt + schema_hint
        
        # 强调 JSON 格式
        json_system = (system_prompt or "") + "\n你必须只返回有效的 JSON，不要包含任何其他文字或代码块标记。"
        
        response = self.chat(prompt, system_prompt=json_system.strip(), temperature=temperature, **kwargs)
        
        if not response:
            return None
        
        return extract_json_from_response(response)


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 响应中提取 JSON
    
    支持：
    - 纯 JSON 文本
    - ```json ... ``` 代码块
    - 混合文本中的 JSON
    """
    import re
    
    text = (text or "").strip()
    
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 移除代码块标记
    if text.startswith("```"):
        text = re.sub(r'^\s*```(?:json)?\s*', '', text, flags=re.I)
        text = re.sub(r'\s*```\s*$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
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
    
    logger.warning(f"无法从响应中提取 JSON: {text[:100]}...")
    return None


# 便捷函数（使用默认客户端）
_default_client: Optional[LLMClient] = None

def _get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def llm_chat(prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
    """便捷函数：调用 LLM 对话"""
    return _get_default_client().chat(prompt, system_prompt=system_prompt, **kwargs)


def llm_chat_json(prompt: str, system_prompt: Optional[str] = None, schema: Optional[Dict] = None, **kwargs) -> Optional[Dict]:
    """便捷函数：调用 LLM 并解析 JSON"""
    return _get_default_client().chat_json(prompt, system_prompt=system_prompt, schema=schema, **kwargs)
