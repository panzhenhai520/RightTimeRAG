#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#


import json
import logging
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from typing import Any
from urllib.parse import urljoin
import tiktoken

from common.file_utils import get_project_base_directory

tiktoken_cache_dir = get_project_base_directory()
os.environ["TIKTOKEN_CACHE_DIR"] = tiktoken_cache_dir
# encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")
encoder = tiktoken.get_encoding("cl100k_base")

TOKENIZER_PROBE_TTL_SECONDS = int(os.environ.get("RAGFLOW_TOKENIZER_PROBE_TTL_SECONDS", "300"))
TOKENIZER_HTTP_TIMEOUT_SECONDS = float(os.environ.get("RAGFLOW_TOKENIZER_HTTP_TIMEOUT_SECONDS", "1.5"))
TOKENIZER_DYNAMIC_ENABLED = os.environ.get("RAGFLOW_DYNAMIC_TOKENIZER", "1").lower() not in {"0", "false", "no"}
TOKENIZER_USE_CHAT_USAGE = os.environ.get("RAGFLOW_TOKENIZER_USE_CHAT_USAGE", "0").lower() in {"1", "true", "yes"}
TOKENIZER_ENDPOINTS = tuple(
    endpoint.strip()
    for endpoint in os.environ.get("RAGFLOW_TOKENIZER_ENDPOINTS", "/tokenize,/v1/tokenize").split(",")
    if endpoint.strip()
)
HF_TOKENIZER_MODEL_PATHS = tuple(
    path.strip()
    for path in os.environ.get("RAGFLOW_HF_TOKENIZER_PATHS", "").split(",")
    if path.strip()
)
DSV4_ENCODING_PATHS = tuple(
    path.strip()
    for path in os.environ.get("RAGFLOW_DSV4_ENCODING_PATHS", "").split(",")
    if path.strip()
)
DSV4_THINKING_MODE = os.environ.get("RAGFLOW_DSV4_THINKING_MODE", "thinking")
FALLBACK_TOKEN_SAFETY_FACTOR = float(os.environ.get("RAGFLOW_FALLBACK_TOKEN_SAFETY_FACTOR", "1.12"))
DEEPSEEK_FALLBACK_TOKEN_SAFETY_FACTOR = float(os.environ.get("RAGFLOW_DEEPSEEK_FALLBACK_TOKEN_SAFETY_FACTOR", "1.15"))

_TOKENIZER_ENDPOINT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_HF_TOKENIZER_CACHE: dict[str, Any] = {}
_HF_TOKENIZER_UNAVAILABLE: set[str] = set()
_DSV4_ENCODER_CACHE: dict[str, Any] = {}
_DSV4_ENCODER_UNAVAILABLE: set[str] = set()


def _fallback_token_count(string: str) -> int:
    try:
        return len(encoder.encode(string or ""))
    except Exception:
        return max(0, len(str(string or "")) // 3)


def _extract_token_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("token_count", "count", "num_tokens", "length"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    usage = payload.get("usage")
    if isinstance(usage, dict):
        value = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("total_tokens")
        if isinstance(value, int):
            return value
    for key in ("tokens", "input_ids", "ids"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_token_count(data)
    return None


def _candidate_tokenizer_urls(base_url: str) -> list[str]:
    base_url = (base_url or "").rstrip("/")
    if not base_url:
        return []
    bases = [base_url]
    if base_url.endswith("/v1"):
        bases.append(base_url[:-3])
    urls = []
    for base in dict.fromkeys(bases):
        for endpoint in TOKENIZER_ENDPOINTS:
            urls.append(urljoin(base + "/", endpoint.lstrip("/")))
    return list(dict.fromkeys(urls))


def _post_json(url: str, payload: dict, api_key: str | None) -> dict | None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TOKENIZER_HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return json.loads(raw) if raw else {}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _hf_tokenizer_candidates(model_name: str) -> list[str]:
    candidates = _configured_hf_tokenizer_paths(model_name)
    if model_name:
        candidates.append(model_name)
    if "deepseek-v4" in (model_name or "").lower() or "deepseek v4" in (model_name or "").lower():
        candidates.append("deepseek-ai/DeepSeek-V4-Flash")
    return list(dict.fromkeys(candidates))


def _is_deepseek_v4_name(model_name: str) -> bool:
    normalized = (model_name or "").lower()
    return "deepseek-v4" in normalized or "deepseek v4" in normalized


def _normalize_tokenizer_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _tokenizer_path_matches_model(path: str, model_name: str) -> bool:
    if not path or not model_name:
        return False
    normalized_model = _normalize_tokenizer_name(model_name)
    normalized_path = _normalize_tokenizer_name(path)
    if not normalized_model or not normalized_path:
        return False
    if normalized_model in normalized_path or normalized_path in normalized_model:
        return True
    if _is_deepseek_v4_name(model_name) and "deepseekv4" in normalized_path:
        return True
    return False


def _configured_hf_tokenizer_paths(model_name: str) -> list[str]:
    candidates = []
    normalized_model = _normalize_tokenizer_name(model_name)
    for item in HF_TOKENIZER_MODEL_PATHS:
        if "=" in item and not item.startswith("/"):
            pattern, path = item.split("=", 1)
            if _normalize_tokenizer_name(pattern) and _normalize_tokenizer_name(pattern) in normalized_model:
                candidates.append(path)
            continue
        if _tokenizer_path_matches_model(item, model_name):
            candidates.append(item)
    return candidates


def _dsv4_encoding_candidates(model_name: str) -> list[str]:
    candidates = list(DSV4_ENCODING_PATHS)
    for tokenizer_candidate in _hf_tokenizer_candidates(model_name):
        if os.path.isdir(tokenizer_candidate):
            candidates.append(os.path.join(tokenizer_candidate, "encoding", "encoding_dsv4.py"))
            candidates.append(os.path.join(tokenizer_candidate, "encoding_dsv4.py"))
    return list(dict.fromkeys(candidates))


def _load_dsv4_encoder(model_name: str):
    if not _is_deepseek_v4_name(model_name):
        return None
    for candidate in _dsv4_encoding_candidates(model_name):
        if not candidate or candidate in _DSV4_ENCODER_UNAVAILABLE:
            continue
        if candidate in _DSV4_ENCODER_CACHE:
            return _DSV4_ENCODER_CACHE[candidate]
        if not os.path.exists(candidate):
            _DSV4_ENCODER_UNAVAILABLE.add(candidate)
            continue
        try:
            module_dir = os.path.dirname(candidate)
            if module_dir and module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            spec = spec_from_file_location("ragflow_dsv4_encoding", candidate)
            if not spec or not spec.loader:
                raise ImportError(f"Cannot load {candidate}")
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            encode_messages = getattr(module, "encode_messages")
            _DSV4_ENCODER_CACHE[candidate] = encode_messages
            return encode_messages
        except Exception:
            _DSV4_ENCODER_UNAVAILABLE.add(candidate)
    return None


def _load_hf_tokenizer(model_name: str):
    for candidate in _hf_tokenizer_candidates(model_name):
        if not candidate or candidate in _HF_TOKENIZER_UNAVAILABLE:
            continue
        if candidate in _HF_TOKENIZER_CACHE:
            return _HF_TOKENIZER_CACHE[candidate]
        try:
            from transformers import AutoTokenizer  # type: ignore

            tokenizer = AutoTokenizer.from_pretrained(candidate, trust_remote_code=True, local_files_only=True)
            _HF_TOKENIZER_CACHE[candidate] = tokenizer
            return tokenizer
        except Exception:
            _HF_TOKENIZER_UNAVAILABLE.add(candidate)
    return None


@dataclass(frozen=True)
class DynamicTokenCounter:
    model_name: str = ""
    base_url: str = ""
    api_key: str = ""
    provider: str = ""
    safety_factor: float | None = None
    dsv4_thinking_mode: str | None = None

    @classmethod
    def from_model_config(cls, model_config: dict | None, dsv4_thinking_mode: str | None = None):
        model_config = model_config or {}
        model_name = str(model_config.get("llm_name") or model_config.get("model_name") or "")
        base_url = str(model_config.get("api_base") or model_config.get("base_url") or "")
        api_key = str(model_config.get("api_key") or "")
        provider = str(model_config.get("llm_factory") or "")
        return cls(model_name=model_name, base_url=base_url, api_key=api_key, provider=provider, dsv4_thinking_mode=dsv4_thinking_mode)

    def _cache_key(self, payload_kind: str) -> tuple[str, str, str]:
        return ((self.base_url or "").rstrip("/"), self.model_name or "", payload_kind)

    @property
    def fallback_safety_factor(self) -> float:
        if self.safety_factor:
            return self.safety_factor
        name = f"{self.provider} {self.model_name}".lower()
        if "deepseek" in name:
            return DEEPSEEK_FALLBACK_TOKEN_SAFETY_FACTOR
        return FALLBACK_TOKEN_SAFETY_FACTOR

    @property
    def resolved_dsv4_thinking_mode(self) -> str:
        mode = (self.dsv4_thinking_mode or DSV4_THINKING_MODE or "thinking").strip().lower()
        return "thinking" if mode == "thinking" else "chat"

    def count_text(self, text: str) -> int:
        text = str(text or "")
        if not text:
            return 0
        tokenizer = _load_hf_tokenizer(self.model_name)
        if tokenizer is not None:
            try:
                return len(tokenizer.encode(text, add_special_tokens=False))
            except Exception:
                pass
        remote_count = self._remote_count({"model": self.model_name, "prompt": text})
        if remote_count is not None:
            return remote_count
        return math.ceil(_fallback_token_count(text) * self.fallback_safety_factor)

    def count_messages(self, messages: list[dict]) -> int:
        clean_messages = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages or []
        ]
        tokenizer = _load_hf_tokenizer(self.model_name)
        if tokenizer is not None:
            dsv4_encoder = _load_dsv4_encoder(self.model_name)
            if dsv4_encoder is not None:
                try:
                    prompt = dsv4_encoder(clean_messages, thinking_mode=self.resolved_dsv4_thinking_mode)
                    return len(tokenizer.encode(prompt, add_special_tokens=False))
                except Exception:
                    pass
            try:
                if hasattr(tokenizer, "apply_chat_template"):
                    return len(tokenizer.apply_chat_template(clean_messages, tokenize=True, add_generation_prompt=False))
            except Exception:
                pass
            try:
                return sum(len(tokenizer.encode(m["content"], add_special_tokens=False)) + 4 for m in clean_messages) + 2
            except Exception:
                pass
        remote_count = self._remote_count({"model": self.model_name, "messages": clean_messages})
        if remote_count is not None:
            return remote_count
        # OpenAI-style chat templates add role and separator tokens. Keep this
        # deliberately conservative when the real model tokenizer is unavailable.
        return sum(self.count_text(m["content"]) + 4 for m in clean_messages) + 2

    def truncate_text(self, text: str, max_tokens: int) -> str:
        max_tokens = max(0, int(max_tokens))
        if max_tokens <= 0:
            return ""
        tokenizer = _load_hf_tokenizer(self.model_name)
        if tokenizer is not None:
            try:
                return tokenizer.decode(tokenizer.encode(str(text or ""), add_special_tokens=False)[:max_tokens])
            except Exception:
                pass
        # Remote tokenizer APIs usually do not expose decode, so truncation uses
        # the local encoder and reserves slack through count_text's safety factor.
        return encoder.decode(encoder.encode(str(text or ""))[:max_tokens])

    def _remote_count(self, payload: dict) -> int | None:
        if not TOKENIZER_DYNAMIC_ENABLED or not self.base_url or not self.model_name:
            return None

        payload_kind = "messages" if payload.get("messages") else "text"
        cache_key = self._cache_key(payload_kind)
        now = time.time()
        cached = _TOKENIZER_ENDPOINT_CACHE.get(cache_key)
        if cached and cached.get("unavailable_until", 0) > now:
            return None

        endpoints = [cached["url"]] if cached and cached.get("url") else _candidate_tokenizer_urls(self.base_url)
        for url in endpoints:
            resp = _post_json(url, payload, self.api_key)
            count = _extract_token_count(resp)
            if count is not None:
                _TOKENIZER_ENDPOINT_CACHE[cache_key] = {"url": url, "unavailable_until": 0}
                return count

        if TOKENIZER_USE_CHAT_USAGE and payload.get("messages"):
            count = self._count_with_chat_usage(payload["messages"])
            if count is not None:
                return count

        _TOKENIZER_ENDPOINT_CACHE[cache_key] = {"url": None, "unavailable_until": now + TOKENIZER_PROBE_TTL_SECONDS}
        logging.debug("Tokenizer endpoint unavailable for model=%s base_url=%s; using local fallback", self.model_name, self.base_url)
        return None

    def _count_with_chat_usage(self, messages: list[dict]) -> int | None:
        # Disabled by default: it performs a real generation request and is only
        # intended for controlled diagnostics when no tokenize endpoint exists.
        base = (self.base_url or "").rstrip("/")
        if not base:
            return None
        url = base if base.endswith("/chat/completions") else urljoin(base + "/", "chat/completions")
        payload = {"model": self.model_name, "messages": messages, "max_tokens": 1, "stream": False}
        resp = _post_json(url, payload, self.api_key)
        return _extract_token_count(resp)


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    return _fallback_token_count(string)

def total_token_count_from_response(resp):
    """
    Extract token count from LLM response in various formats.

    Handles None responses and different response structures from various LLM providers.
    Returns 0 if token count cannot be determined.
    """
    if resp is None:
        return 0

    try:
        if hasattr(resp, "usage") and hasattr(resp.usage, "total_tokens"):
            return resp.usage.total_tokens
    except Exception:
        pass

    try:
        if hasattr(resp, "usage_metadata") and hasattr(resp.usage_metadata, "total_tokens"):
            return resp.usage_metadata.total_tokens
    except Exception:
        pass

    try:
        if hasattr(resp, "meta") and hasattr(resp.meta, "billed_units") and hasattr(resp.meta.billed_units, "input_tokens"):
            return resp.meta.billed_units.input_tokens
    except Exception:
        pass

    if isinstance(resp, dict) and 'usage' in resp and 'total_tokens' in resp['usage']:
        try:
            return resp["usage"]["total_tokens"]
        except Exception:
            pass

    if isinstance(resp, dict) and 'usage' in resp and 'input_tokens' in resp['usage'] and 'output_tokens' in resp['usage']:
        try:
            return resp["usage"]["input_tokens"] + resp["usage"]["output_tokens"]
        except Exception:
            pass

    if isinstance(resp, dict) and 'meta' in resp and 'tokens' in resp['meta'] and 'input_tokens' in resp['meta']['tokens'] and 'output_tokens' in resp['meta']['tokens']:
        try:
            return resp["meta"]["tokens"]["input_tokens"] + resp["meta"]["tokens"]["output_tokens"]
        except Exception:
            pass
    return 0


def truncate(string: str, max_len: int) -> str:
    """Returns truncated text if the length of text exceed max_len."""
    return encoder.decode(encoder.encode(string)[:max_len])
