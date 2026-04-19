"""
LLM 클라이언트 래퍼
OpenAI 와 Anthropic 두 가지 공급자 지원
"""

import json
import re
from typing import Optional, Dict, Any, List

from ..config import Config


class LLMClient:
    """LLM 클라이언트 — OpenAI 와 Anthropic 지원"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.provider = provider or Config.LLM_PROVIDER

        if not self.api_key:
            raise ValueError("LLM_API_KEY 가 설정되지 않았습니다")

        if self.provider == 'anthropic':
            from anthropic import Anthropic
            self.anthropic_client = Anthropic(api_key=self.api_key)
            self.client = None
        else:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.anthropic_client = None

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        채팅 요청 전송

        Args:
            messages: 메시지 목록
            temperature: 온도 파라미터
            max_tokens: 최대 토큰 수
            response_format: 응답 형식（예: JSON 모드）

        Returns:
            모델 응답 텍스트
        """
        # Pipeline 오케스트레이터가 현재 실행 중이면 LLM 호출 카운터 증가.
        # contextvar default=0이므로 오케스트레이터 외부에서 호출돼도 영향 없음.
        # 역방향 import 회피를 위해 lazy import. 실패 시 조용히 스킵.
        try:
            from ..services.pipeline_orchestrator import llm_call_counter
            llm_call_counter.set(llm_call_counter.get() + 1)
        except Exception:
            pass

        if self.provider == 'anthropic':
            return self._chat_anthropic(messages, temperature, max_tokens, response_format)
        else:
            return self._chat_openai(messages, temperature, max_tokens, response_format)

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict]
    ) -> str:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 일부 모델（예: MiniMax M2.5）은 content에 <think> 사고 내용을 포함하므로 제거 필요
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict]
    ) -> str:
        # Extract system message if present
        system_text = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                user_messages.append(msg)

        # If JSON mode requested, add instruction to system prompt
        if response_format and response_format.get("type") == "json_object":
            system_text += "\n\nIMPORTANT: You must respond with valid JSON only. No markdown, no explanation, just a JSON object."

        # Ensure messages alternate properly (Anthropic requires user first)
        if not user_messages or user_messages[0]["role"] != "user":
            user_messages.insert(0, {"role": "user", "content": "Please proceed."})

        # Fix consecutive same-role messages
        fixed_messages = []
        for msg in user_messages:
            if fixed_messages and fixed_messages[-1]["role"] == msg["role"]:
                fixed_messages[-1]["content"] += "\n\n" + msg["content"]
            else:
                fixed_messages.append({"role": msg["role"], "content": msg["content"]})

        kwargs = {
            "model": self.model,
            "messages": fixed_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_text.strip():
            kwargs["system"] = system_text.strip()

        response = self.anthropic_client.messages.create(**kwargs)
        content = response.content[0].text
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        채팅 요청 전송 및 JSON 반환

        Args:
            messages: 메시지 목록
            temperature: 온도 파라미터
            max_tokens: 최대 토큰 수

        Returns:
            파싱된 JSON 객체
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # 마크다운 코드 블록 마커 제거
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"LLM이 반환한 JSON 형식이 올바르지 않습니다: {cleaned_response[:500]}")
