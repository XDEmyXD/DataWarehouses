import os
import json
from typing import Optional, Callable
from dotenv import load_dotenv

load_dotenv()


class LLMService:
    def __init__(self, tool_runner: Optional[Callable] = None, local_backend: Optional[str] = None):
        """Initialize the LLM service.

        tool_runner: optional callable(tool_name, params) used to execute MCP tools.
        """
        self.tool_runner = tool_runner
        self.local_backend = local_backend
        try:
            from app.mistral_adapter import MistralAdapter

            self.mistral_adapter = MistralAdapter()
        except Exception:
            self.mistral_adapter = None

    def is_configured(self):
        return self.mistral_adapter is not None and self.mistral_adapter.is_configured()

    def _build_messages(self, prompt, extra_context=None):
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a responsible financial analytics assistant for a student-friendly data warehouse platform. "
                    "Use the available dataset metadata and analytics summaries to answer clearly and without giving investment advice."
                ),
            }
        ]
        if extra_context:
            messages.append({"role": "system", "content": extra_context})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_function_definitions(self):
        """Convert TOOL_DEFINITIONS into function definitions.

        This is a generic mapping: all parameters are treated as strings.
        """
        try:
            from app.mcp_tools import TOOL_DEFINITIONS
        except Exception:
            return []

        functions = []
        for name, info in TOOL_DEFINITIONS.items():
            params = info.get("params") or {}
            properties = {}
            required = []
            for p_name, p_type in params.items():
                properties[p_name] = {"type": "string"}
                # treat declared 'string' as required
                if p_type == "string":
                    required.append(p_name)

            func = {
                "name": name,
                "description": info.get("description", ""),
                "parameters": {"type": "object", "properties": properties, "required": required},
            }
            functions.append(func)

        return functions

    def generate(self, prompt, model=None, use_functions: bool = False):
        """Simple generate method (no tool-calling by default).

        If `use_functions` is True and tools are available, this will attempt
        to use the function-calling flow via `generate_with_tools`.
        """
        if not self.is_configured():
            raise RuntimeError("LLM is not configured. Configure the Mistral adapter with MISTRAL_API_KEY.")

        if use_functions:
            functions = self._build_function_definitions()
            messages = self._build_messages(prompt)
            return self.mistral_adapter.generate_with_tools(messages, functions, tool_runner=self.tool_runner)

        messages = self._build_messages(prompt)
        return self.mistral_adapter.generate(messages)

    def generate_with_tools(self, prompt, model=None):
        """Use function-calling to let the model call MCP tools.

        Flow:
        1. Send messages + function definitions to the model.
        2. If model requests a function call, execute it via `tool_runner` or the
           MCP `call_tool` and provide the tool output back to the model.
        3. Return the final assistant message.
        """
        if not self.is_configured():
            raise RuntimeError("LLM is not configured. Configure the Mistral adapter with MISTRAL_API_KEY.")

        functions = self._build_function_definitions()
        messages = self._build_messages(prompt)
        return self.mistral_adapter.generate_with_tools(messages, functions, tool_runner=self.tool_runner)

    def explain_asset(self, asset_id, start_date, end_date, summary_payload):
        if not self.is_configured():
            return summary_payload.get("summary", "No summary available.")

        prompt = (
            f"Please explain the performance of asset '{asset_id}' between {start_date} and {end_date}. "
            "Use the analytics summary below from the platform. Keep the answer simple and student-friendly. "
            "Do not provide investment advice.\n\n"
            f"Analytics Summary:\n{summary_payload.get('summary', '')}"
        )
        # Prefer the function-enabled flow so the model can request tool data if needed
        try:
            return self.generate_with_tools(prompt)
        except Exception:
            return self.generate(prompt)
