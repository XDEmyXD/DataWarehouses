import os
import json
import re
from typing import List, Optional, Callable

import requests


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    match = re.search(r"(\{[\s\S]*\})", text)
    if not match:
        return None
    candidate = match.group(1)
    try:
        return json.loads(candidate)
    except Exception:
        try:
            return json.loads(candidate.replace("'", '"'))
        except Exception:
            return None


class MistralAdapter:
    """Simple HTTP adapter for a Mistral-compatible API.

    This adapter uses a prompt-based JSON tool-calling protocol (the model
    returns a JSON object when it wants to call a tool). Configure via env:
      - MISTRAL_API_KEY
      - MISTRAL_API_URL (optional; defaults to https://api.mistral.ai/v1/chat/completions)
      - MISTRAL_MODEL (optional model identifier)
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        self.api_url = api_url or os.getenv("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions")
        # If a base URL (e.g. https://api.mistral.ai/v1) is provided, ensure the adapter
        # uses the chat completions endpoint by appending the path when missing.
        if not self.api_url.rstrip('/').endswith('/chat/completions'):
            self.api_url = self.api_url.rstrip('/') + '/chat/completions'
        self.model = model or os.getenv("MISTRAL_MODEL")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_url)

    def _call_api(self, payload: dict, timeout: int = 30) -> Optional[dict]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=timeout)
        except Exception:
            return None

        try:
            return resp.json()
        except Exception:
            return None

    def _parse_response_text(self, resp_json: dict) -> str:
        if not resp_json:
            return ""
        # Try common places for text
        choices = resp_json.get("choices") or []
        if choices and isinstance(choices, list):
            first = choices[0]
            if isinstance(first, dict):
                # OpenAI-like shape
                msg = first.get("message") or {}
                if isinstance(msg, dict):
                    return msg.get("content") or msg.get("text") or ""
                return first.get("text") or ""

        # Other shapes
        return resp_json.get("output") or resp_json.get("text") or ""

    def _messages_to_prompt(self, messages: List[dict]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"[{role.upper()}]\n{content}\n")
        return "\n".join(parts)

    def generate(self, messages: List[dict], temperature: float = 0.2, max_tokens: int = 512) -> str:
        # Prefer sending structured `messages` payload compatible with the
        # Mistral chat completions API.
        payload = {"messages": messages}
        if self.model:
            payload["model"] = self.model

        resp_json = self._call_api(payload)
        return self._parse_response_text(resp_json)

    def generate_with_tools(self, messages: List[dict], functions: List[dict], tool_runner: Optional[Callable] = None, max_steps: int = 3, temperature: float = 0.2, max_tokens: int = 512) -> str:
        # Build a prompt encouraging strict JSON tool calls
        prompt = (
            "You are a financial analytics assistant. When you want to call a platform tool, "
            "output ONLY a single JSON object with the shape {\"tool\": \"tool_name\", \"params\": {...}} and nothing else. "
            "If you do not need to call a tool, answer in plain natural language.\n\n"
        )

        # add messages
        prompt += self._messages_to_prompt(messages)

        # show available tools
        if functions:
            prompt += "\nAvailable tools:\n"
            for f in functions:
                name = f.get("name")
                desc = f.get("description", "")
                params = f.get("parameters", {}).get("properties", {})
                param_list = ", ".join([f"{k}: {v.get('type','string')}" for k, v in params.items()])
                prompt += f"- {name}({param_list}): {desc}\n"

        for step in range(max_steps):
            # Send the prompt as a single user message in a `messages` array.
            payload = {"messages": [{"role": "user", "content": prompt}]}
            if self.model:
                payload["model"] = self.model

            resp_json = self._call_api(payload)
            out = self._parse_response_text(resp_json)
            call_obj = _extract_json_object(out)
            if not call_obj:
                return out or ""

            tool_name = call_obj.get("tool") or call_obj.get("function")
            params = call_obj.get("params") or call_obj.get("arguments") or {}

            if not tool_name:
                return out

            # Execute tool
            try:
                if tool_runner:
                    tool_result = tool_runner(tool_name, params)
                else:
                    from app.mcp_tools import call_tool as _call_tool

                    tool_result = _call_tool(tool_name, params)
            except Exception as exc:
                tool_result = {"status": "error", "message": str(exc)}

            prompt += f"\n[Tool called: {tool_name} with params {json.dumps(params)}]\nTool result: {json.dumps(tool_result)}\nAssistant:"

        return self._parse_response_text(self._call_api({"input": prompt, "model": self.model})) or ""
