#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
import asyncio
import logging
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from quart import request

from api.apps import login_required, current_user
from api.db.services.tenant_llm_service import LLMFactoriesService, TenantLLMService
from api.db.services.llm_service import LLMService
from api.utils.api_utils import get_allowed_llm_factories, get_data_error_result, get_json_result, get_request_json, server_error_response, validate_request
from common.constants import StatusEnum, LLMType
from api.db.db_models import TenantLLM


DS4_HEALTH_STATUS_FILE = Path(
    os.environ.get(
        "RAGFLOW_DS4_HEALTH_STATUS_FILE",
        "/home/xsuper/app/newapp/runtime/ds4/ds4-health.json",
    )
)
DS4_HEALTH_STALE_SECONDS = int(
    os.environ.get("RAGFLOW_DS4_HEALTH_STALE_SECONDS", "120")
)
XINFERENCE_DEFAULT_MODEL_ENDPOINTS = [
    item.strip()
    for item in os.environ.get(
        "RAGFLOW_XINFERENCE_MODEL_ENDPOINTS",
        "http://127.0.0.1:9997/v1/models,http://127.0.0.1:9998/v1/models",
    ).split(",")
    if item.strip()
]
XINFERENCE_MODEL_LIST_TIMEOUT = float(
    os.environ.get("RAGFLOW_XINFERENCE_MODEL_LIST_TIMEOUT", "0.8")
)


def _build_ds4_health_level(payload: dict) -> str:
    state = str(payload.get("state") or "").lower()
    if state in {"maintenance", "restarting"}:
        return "critical"
    if state in {"starting", "warming", "degraded"}:
        return "warning"
    usage_percent = payload.get("usage_percent")
    try:
        usage = float(usage_percent)
    except (TypeError, ValueError):
        return "unknown"
    if usage >= 86:
        return "critical"
    if usage >= 80:
        return "warning"
    if usage >= 65:
        return "watch"
    return "healthy"


def _normalize_xinference_models_endpoint(api_base: str | None) -> str | None:
    api_base = (api_base or "").strip()
    if not api_base:
        return None
    if not api_base.startswith(("http://", "https://")):
        api_base = f"http://{api_base}"
    api_base = api_base.rstrip("/")
    if api_base.endswith("/v1/models"):
        return api_base
    if api_base.endswith("/v1"):
        return f"{api_base}/models"
    return f"{api_base}/v1/models"


def _fetch_xinference_loaded_model_ids(objs) -> set[str]:
    endpoints = set(XINFERENCE_DEFAULT_MODEL_ENDPOINTS)
    for obj in objs:
        if getattr(obj, "llm_factory", None) != "Xinference":
            continue
        endpoint = _normalize_xinference_models_endpoint(getattr(obj, "api_base", None))
        if endpoint:
            endpoints.add(endpoint)

    loaded: set[str] = set()
    for endpoint in endpoints:
        try:
            with urllib.request.urlopen(endpoint, timeout=XINFERENCE_MODEL_LIST_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for model in payload.get("data") or []:
                for key in ("id", "model_name"):
                    value = str(model.get(key) or "").strip().lower()
                    if value:
                        loaded.add(value)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            logging.info("Skip unavailable Xinference model endpoint %s: %s", endpoint, exc)
    return loaded


def _is_xinference_model_loaded(model_name: str, loaded_model_ids: set[str]) -> bool:
    if not loaded_model_ids:
        return True
    name = str(model_name or "").strip().lower()
    if not name:
        return False
    candidates = {name, Path(name).name.lower()}
    return bool(candidates & loaded_model_ids)


@manager.route("/ds4/status", methods=["GET"])  # noqa: F821
@login_required
def ds4_status():
    now = int(time.time())
    default_payload = {
        "service": "ds4-server-ragflow.service",
        "base_url": os.environ.get(
            "RAGFLOW_DS4_MODELS_URL",
            "http://127.0.0.1:8106/v1/models",
        ).replace("/v1/models", ""),
        "state": "unknown",
        "reason": "health_status_missing",
        "ready": False,
        "blocking": False,
        "context_length": 131072,
        "live_tokens": None,
        "remaining_tokens": None,
        "usage_percent": None,
        "restart_threshold": None,
        "restart_usage_percent": None,
        "min_free_tokens": None,
        "maintenance_progress": None,
        "maintenance_phase": None,
        "maintenance_started_at": None,
        "restart_count": None,
        "updated_at": None,
        "stale": True,
    }
    try:
        if DS4_HEALTH_STATUS_FILE.exists():
            payload = json.loads(DS4_HEALTH_STATUS_FILE.read_text(encoding="utf-8"))
        else:
            payload = default_payload
        updated_at = payload.get("updated_at")
        stale = True
        if isinstance(updated_at, (int, float)):
            stale = now - int(updated_at) > DS4_HEALTH_STALE_SECONDS
        payload["stale"] = stale
        if stale and payload.get("state") == "ready":
            payload["state"] = "degraded"
            payload["reason"] = "health_status_stale"
            payload["ready"] = False
        payload["level"] = _build_ds4_health_level(payload)
        return get_json_result(data=payload)
    except Exception as e:
        logging.exception("Failed to read DS4 health status")
        fallback = {**default_payload, "reason": f"health_status_error: {e}"}
        fallback["level"] = "unknown"
        return get_json_result(data=fallback)


def _resolve_my_llm_is_tools(o_dict: dict) -> bool:
    decode_api_key_config = getattr(TenantLLMService, "_decode_api_key_config", None)
    if callable(decode_api_key_config):
        _, is_tools, _ = decode_api_key_config(o_dict.get("api_key", ""))
        if is_tools is not None:
            return bool(is_tools)

    try:
        base_name, fid = TenantLLMService.split_model_name_and_factory(o_dict["llm_name"])
        llm_cfg = LLMService.query(llm_name=base_name, fid=fid) if fid else LLMService.query(llm_name=base_name)
        if not llm_cfg and fid:
            llm_cfg = LLMService.query(llm_name=base_name)
        return bool(llm_cfg[0].is_tools) if llm_cfg else False
    except Exception:
        return False


@manager.route("/factories", methods=["GET"])  # noqa: F821
@login_required
def factories():
    try:
        fac = get_allowed_llm_factories()
        fac = [f.to_dict() for f in fac if f.name not in ["Youdao", "FastEmbed", "BAAI", "Builtin", "siliconflow_intl"]]
        llms = LLMService.get_all()
        mdl_types = {}
        for m in llms:
            if m.status != StatusEnum.VALID.value:
                continue
            if m.fid not in mdl_types:
                mdl_types[m.fid] = set([])
            mdl_types[m.fid].add(m.model_type)
        for f in fac:
            f["model_types"] = list(
                mdl_types.get(
                    f["name"],
                    [LLMType.CHAT, LLMType.EMBEDDING, LLMType.RERANK, LLMType.IMAGE2TEXT, LLMType.SPEECH2TEXT, LLMType.TTS, LLMType.OCR],
                )
            )

        return get_json_result(data=fac)
    except Exception as e:
        return server_error_response(e)


@manager.route("/set_api_key", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory", "api_key")
async def set_api_key():
    req = await get_request_json()
    from rag.llm import ChatModel, EmbeddingModel, RerankModel

    # test if api key works
    chat_passed, embd_passed, rerank_passed = False, False, False
    factory = req["llm_factory"]
    base_url = req.get("base_url", "")
    source_factory = req.get("source_fid", factory)
    extra = {"provider": factory}
    timeout_seconds = int(os.environ.get("LLM_TIMEOUT_SECONDS", 10))
    source_llms = list(LLMService.query(fid=source_factory))
    if not source_llms:
        msg = f"No models configured for {factory} (source: {source_factory})."
        if req.get("verify", False):
            return get_json_result(data={"message": msg, "success": False})
        return get_data_error_result(message=msg)

    msg = ""
    for llm in source_llms:
        if not embd_passed and llm.model_type == LLMType.EMBEDDING.value:
            assert factory in EmbeddingModel, f"Embedding model from {factory} is not supported yet."
            mdl = EmbeddingModel[factory](req["api_key"], llm.llm_name, base_url=base_url)
            try:
                arr, tc = await asyncio.wait_for(
                    asyncio.to_thread(mdl.encode, ["Test if the api key is available"]),
                    timeout=timeout_seconds,
                )
                if len(arr[0]) == 0:
                    raise Exception("Fail")
                embd_passed = True
            except Exception as e:
                msg += f"\nFail to access embedding model({llm.llm_name}) using this api key." + str(e)
        elif not chat_passed and llm.model_type == LLMType.CHAT.value:
            assert factory in ChatModel, f"Chat model from {factory} is not supported yet."
            mdl = ChatModel[factory](req["api_key"], llm.llm_name, base_url=base_url, **extra)
            try:
                async def check_streamly():
                    async for chunk in mdl.async_chat_streamly(
                        None,
                        [{"role": "user", "content": "Hi"}],
                        {"temperature": 0.9},
                    ):
                        if chunk and isinstance(chunk, str) and chunk.find("**ERROR**") < 0:
                            return True
                    return False

                result = await asyncio.wait_for(check_streamly(), timeout=timeout_seconds)
                if result:
                    chat_passed = True
                else:
                    raise Exception("No valid response received")
            except Exception as e:
                msg += f"\nFail to access model({llm.fid}/{llm.llm_name}) using this api key." + str(e)
        elif not rerank_passed and llm.model_type == LLMType.RERANK.value:
            assert factory in RerankModel, f"Re-rank model from {factory} is not supported yet."
            mdl = RerankModel[factory](req["api_key"], llm.llm_name, base_url=base_url)
            try:
                arr, tc = await asyncio.wait_for(
                    asyncio.to_thread(mdl.similarity, "What's the weather?", ["Is it sunny today?"]),
                    timeout=timeout_seconds,
                )
                if len(arr) == 0 or tc == 0:
                    raise Exception("Fail")
                rerank_passed = True
                logging.debug(f"passed model rerank {llm.llm_name}")
            except Exception as e:
                msg += f"\nFail to access model({llm.fid}/{llm.llm_name}) using this api key." + str(e)
        if any([embd_passed, chat_passed, rerank_passed]):
            msg = ""
            break

    if req.get("verify", False):
        return get_json_result(data={"message": msg, "success": len(msg.strip())==0})

    if msg:
        return get_data_error_result(message=msg)

    llm_config = {"api_key": req["api_key"], "api_base": base_url}
    for n in ["model_type", "llm_name"]:
        if n in req:
            llm_config[n] = req[n]

    for llm in source_llms:
        llm_config["max_tokens"] = llm.max_tokens
        if not TenantLLMService.filter_update([TenantLLM.tenant_id == current_user.id, TenantLLM.llm_factory == factory, TenantLLM.llm_name == llm.llm_name], llm_config):
            TenantLLMService.save(
                tenant_id=current_user.id,
                llm_factory=factory,
                llm_name=llm.llm_name,
                model_type=llm.model_type,
                api_key=llm_config["api_key"],
                api_base=llm_config["api_base"],
                max_tokens=llm_config["max_tokens"],
            )

    return get_json_result(data=True)


@manager.route("/add_llm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory")
async def add_llm():
    req = await get_request_json()
    from rag.llm import ChatModel, CvModel, EmbeddingModel, OcrModel, RerankModel, Seq2txtModel, TTSModel

    factory = req["llm_factory"]
    llm_name = req.get("llm_name")
    timeout_seconds = int(os.environ.get("LLM_TIMEOUT_SECONDS", 10))

    if factory not in [f.name for f in get_allowed_llm_factories()]:
        return get_data_error_result(message=f"LLM factory {factory} is not allowed")

    # When editing an existing model the frontend leaves the api_key input blank
    # and strips it from the payload, so req["api_key"] is missing. Without a
    # fallback the validation below would run with the "x" placeholder and the
    # upstream provider would return "Your API key is invalid" — recover the
    # saved key from DB. Use only the *decoded* api_key (never the raw JSON
    # payload) so factories that pack extra fields into api_key
    # (OpenRouter, Bedrock, …) can rebuild their JSON correctly with whatever
    # new fields the user did provide via apikey_json.
    if req.get("api_key") is None and llm_name:
        _LLM_NAME_SUFFIX = {
            "LocalAI": "___LocalAI",
            "HuggingFace": "___HuggingFace",
            "OpenAI-API-Compatible": "___OpenAI-API",
            "VLLM": "___VLLM",
        }
        saved_llm_name = llm_name + _LLM_NAME_SUFFIX.get(factory, "")
        logging.debug(
            "add_llm: attempting api_key recovery factory=%s llm_name=%s saved_llm_name=%s tenant_id=%s",
            factory, llm_name, saved_llm_name, current_user.id,
        )
        existing_llms = TenantLLMService.query(
            tenant_id=current_user.id,
            llm_factory=factory,
            llm_name=saved_llm_name,
        )
        logging.debug(
            "add_llm: api_key recovery query matched=%d factory=%s saved_llm_name=%s",
            len(existing_llms) if existing_llms else 0, factory, saved_llm_name,
        )
        if existing_llms:
            existing_api_key, _, _ = TenantLLMService._decode_api_key_config(
                existing_llms[0].api_key
            )
            logging.debug(
                "add_llm: api_key recovery decoded=%s factory=%s saved_llm_name=%s",
                "present" if existing_api_key else "absent", factory, saved_llm_name,
            )
            if existing_api_key:
                req["api_key"] = existing_api_key
                logging.info(
                    "add_llm: recovered saved api_key from existing record factory=%s saved_llm_name=%s tenant_id=%s",
                    factory, saved_llm_name, current_user.id,
                )

    api_key = req.get("api_key", "x")

    def apikey_json(keys):
        nonlocal req
        return json.dumps({k: req.get(k, "") for k in keys})

    if factory == "VolcEngine":
        # For VolcEngine, due to its special authentication method
        # Assemble ark_api_key model_id into api_key; keep endpoint_id in backend payload for compatibility
        api_key = apikey_json(["ark_api_key", "endpoint_id"])

    elif factory == "Tencent Cloud":
        req["api_key"] = apikey_json(["tencent_cloud_sid", "tencent_cloud_sk"])
        return await set_api_key()

    elif factory == "Bedrock":
        # For Bedrock, due to its special authentication method
        # Assemble bedrock_ak, bedrock_sk, bedrock_region
        # Write into req["api_key"] to prevent the "existing key" override logic from replacing it
        req["api_key"] = apikey_json(["auth_mode", "bedrock_ak", "bedrock_sk", "bedrock_region", "aws_role_arn"])
        api_key = req["api_key"]

    elif factory == "LocalAI":
        llm_name += "___LocalAI"

    elif factory == "HuggingFace":
        llm_name += "___HuggingFace"

    elif factory == "OpenAI-API-Compatible":
        llm_name += "___OpenAI-API"

    elif factory == "VLLM":
        llm_name += "___VLLM"

    elif factory == "XunFei Spark":
        if req["model_type"] == "chat":
            api_key = req.get("spark_api_password", "")
        elif req["model_type"] == "tts":
            api_key = apikey_json(["spark_app_id", "spark_api_secret", "spark_api_key"])

    elif factory == "BaiduYiyan":
        api_key = apikey_json(["yiyan_ak", "yiyan_sk"])

    elif factory == "Fish Audio":
        api_key = apikey_json(["fish_audio_ak", "fish_audio_refid"])

    elif factory == "Google Cloud":
        api_key = apikey_json(["google_project_id", "google_region", "google_service_account_key"])

    elif factory == "Azure-OpenAI":
        api_key = apikey_json(["api_key", "api_version"])

    elif factory == "OpenRouter":
        api_key = apikey_json(["api_key", "provider_order"])

    elif factory == "MinerU":
        api_key = apikey_json(["api_key", "provider_order"])

    elif factory == "PaddleOCR":
        api_key = apikey_json(["api_key", "provider_order"])

    elif factory == "OpenDataLoader":
        api_key = apikey_json(["api_key", "provider_order"])

    llm = {
        "tenant_id": current_user.id,
        "llm_factory": factory,
        "model_type": req["model_type"],
        "llm_name": llm_name,
        "api_base": req.get("api_base", ""),
        "api_key": api_key,
        "max_tokens": req.get("max_tokens"),
    }

    msg = ""
    mdl_nm = llm["llm_name"].split("___")[0]
    extra = {"provider": factory}
    model_type = llm["model_type"]
    model_api_key = llm["api_key"]
    model_base_url = llm.get("api_base", "")
    # Local DS4 (thinking model) needs a longer validation timeout — it queues
    # inference requests and reasoning tokens arrive after the queue drains.
    if model_base_url and "127.0.0.1:8106" in model_base_url:
        timeout_seconds = max(timeout_seconds, 120)
    match model_type:
        case LLMType.EMBEDDING.value:
            assert factory in EmbeddingModel, f"Embedding model from {factory} is not supported yet."
            mdl = EmbeddingModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
            try:
                arr, tc = await asyncio.wait_for(
                    asyncio.to_thread(mdl.encode, ["Test if the api key is available"]),
                    timeout=timeout_seconds,
                )
                if len(arr[0]) == 0:
                    raise Exception("Fail")
            except Exception as e:
                msg += f"\nFail to access embedding model({mdl_nm})." + str(e)
        case LLMType.CHAT.value:
            assert factory in ChatModel, f"Chat model from {factory} is not supported yet."
            mdl = ChatModel[factory](
                key=model_api_key,
                model_name=mdl_nm,
                base_url=model_base_url,
                **extra,
            )
            try:
                async def check_streamly():
                    async for chunk in mdl.async_chat_streamly(
                        None,
                        [{"role": "user", "content": "Hi"}],
                        {"temperature": 0.9},
                    ):
                        if chunk and isinstance(chunk, str) and chunk.find("**ERROR**:") < 0:
                            return True
                    return False

                result = await asyncio.wait_for(check_streamly(), timeout=timeout_seconds)
                if not result:
                    raise Exception("No valid response received")
            except Exception as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)

        case LLMType.RERANK.value:
            assert factory in RerankModel, f"RE-rank model from {factory} is not supported yet."
            try:
                mdl = RerankModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
                arr, tc = await asyncio.wait_for(
                    asyncio.to_thread(mdl.similarity, "Hello~ RAGFlower!", ["Hi, there!", "Ohh, my friend!"]),
                    timeout=timeout_seconds,
                )
                if len(arr) == 0:
                    raise Exception("Not known.")
            except KeyError:
                msg += f"{factory} does not support this model({factory}/{mdl_nm})"
            except Exception as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)

        case LLMType.IMAGE2TEXT.value:
            from rag.utils.base64_image import test_image

            assert factory in CvModel, f"Image to text model from {factory} is not supported yet."
            mdl = CvModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
            try:
                image_data = test_image
                m, tc = await asyncio.wait_for(
                    asyncio.to_thread(mdl.describe, image_data),
                    timeout=timeout_seconds,
                )
                if not tc and m.find("**ERROR**:") >= 0:
                    raise Exception(m)
            except Exception as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)
        case LLMType.TTS.value:
            assert factory in TTSModel, f"TTS model from {factory} is not supported yet."
            mdl = TTSModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
            try:
                def drain_tts():
                    for _ in mdl.tts("Hello~ RAGFlower!"):
                        pass

                await asyncio.wait_for(
                    asyncio.to_thread(drain_tts),
                    timeout=timeout_seconds,
                )
            except RuntimeError as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)
        case LLMType.OCR.value:
            assert factory in OcrModel, f"OCR model from {factory} is not supported yet."
            try:
                mdl = OcrModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
                ok, reason = await asyncio.wait_for(
                    asyncio.to_thread(mdl.check_available),
                    timeout=timeout_seconds,
                )
                if not ok:
                    raise RuntimeError(reason or "Model not available")
            except Exception as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)
        case LLMType.SPEECH2TEXT.value:
            assert factory in Seq2txtModel, f"Speech model from {factory} is not supported yet."
            try:
                mdl = Seq2txtModel[factory](key=model_api_key, model_name=mdl_nm, base_url=model_base_url)
                # TODO: check the availability
            except Exception as e:
                msg += f"\nFail to access model({factory}/{mdl_nm})." + str(e)
        case _:
            raise RuntimeError(f"Unknown model type: {model_type}")

    if req.get("verify", False):
        return get_json_result(data={"message": msg, "success": len(msg.strip()) == 0})

    if msg:
        return get_data_error_result(message=msg)

    if "is_tools" in req:
        llm["api_key"] = TenantLLMService._encode_api_key_config(llm["api_key"], bool(req["is_tools"]))

    if not TenantLLMService.filter_update([TenantLLM.tenant_id == current_user.id, TenantLLM.llm_factory == factory, TenantLLM.llm_name == llm["llm_name"]], llm):
        TenantLLMService.save(**llm)

    return get_json_result(data=True)


@manager.route("/delete_llm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory", "llm_name")
async def delete_llm():
    req = await get_request_json()
    TenantLLMService.filter_delete([TenantLLM.tenant_id == current_user.id, TenantLLM.llm_factory == req["llm_factory"], TenantLLM.llm_name == req["llm_name"]])
    return get_json_result(data=True)


@manager.route("/enable_llm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory", "llm_name")
async def enable_llm():
    req = await get_request_json()
    TenantLLMService.filter_update(
        [TenantLLM.tenant_id == current_user.id, TenantLLM.llm_factory == req["llm_factory"], TenantLLM.llm_name == req["llm_name"]], {"status": str(req.get("status", "1"))}
    )
    return get_json_result(data=True)


@manager.route("/delete_factory", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory")
async def delete_factory():
    req = await get_request_json()
    TenantLLMService.filter_delete([TenantLLM.tenant_id == current_user.id, TenantLLM.llm_factory == req["llm_factory"]])
    return get_json_result(data=True)


@manager.route("/my_llms", methods=["GET"])  # noqa: F821
@login_required
def my_llms():
    try:
        TenantLLMService.ensure_mineru_from_env(current_user.id)
        TenantLLMService.ensure_opendataloader_from_env(current_user.id)
        include_details = request.args.get("include_details", "false").lower() == "true"

        if include_details:
            res = {}
            objs = TenantLLMService.query(tenant_id=current_user.id)
            factories = LLMFactoriesService.query(status=StatusEnum.VALID.value)

            for o in objs:
                o_dict = o.to_dict()
                factory_tags = None
                for f in factories:
                    if f.name == o_dict["llm_factory"]:
                        factory_tags = f.tags
                        break

                if o_dict["llm_factory"] not in res:
                    res[o_dict["llm_factory"]] = {"tags": factory_tags, "llm": []}

                res[o_dict["llm_factory"]]["llm"].append(
                    {
                        "id": o_dict["id"],
                        "type": o_dict["model_type"],
                        "name": o_dict["llm_name"],
                        "used_token": o_dict["used_tokens"],
                        "api_base": o_dict["api_base"] or "",
                        "max_tokens": o_dict["max_tokens"] or 8192,
                        "status": o_dict["status"] or "1",
                        "is_tools": _resolve_my_llm_is_tools(o_dict),
                    }
                )
        else:
            res = {}
            for o in TenantLLMService.get_my_llms(current_user.id):
                if o["llm_factory"] not in res:
                    res[o["llm_factory"]] = {"tags": o["tags"], "llm": []}
                res[o["llm_factory"]]["llm"].append({"id": o["id"], "type": o["model_type"], "name": o["llm_name"], "used_token": o["used_tokens"], "status": o["status"]})

        return get_json_result(data=res)
    except Exception as e:
        return server_error_response(e)


@manager.route("/list", methods=["GET"])  # noqa: F821
@login_required
async def list_app():
    self_deployed = ["FastEmbed", "Ollama", "Xinference", "LocalAI", "LM-Studio", "GPUStack"]
    weighted = []
    model_type = request.args.get("model_type")
    tenant_id = current_user.id
    try:
        TenantLLMService.ensure_mineru_from_env(tenant_id)
        objs = TenantLLMService.query(tenant_id=tenant_id)
        xinference_loaded_model_ids = _fetch_xinference_loaded_model_ids(objs)
        facts = set([o.to_dict()["llm_factory"] for o in objs if o.api_key and o.status == StatusEnum.VALID.value])
        tenant_llm_mapping = {f"{o.llm_name}@{o.llm_factory}": o for o in objs}
        status = {(o.llm_name + "@" + o.llm_factory) for o in objs if o.status == StatusEnum.VALID.value}
        llms = LLMService.get_all()
        llms = [m.to_dict() for m in llms if m.status == StatusEnum.VALID.value and m.fid not in weighted and (m.fid == "Builtin" or (m.llm_name + "@" + m.fid) in status)]
        filtered_llms = []
        for m in llms:
            if m["fid"] == "Xinference" and not _is_xinference_model_loaded(m["llm_name"], xinference_loaded_model_ids):
                continue
            m["id"] = tenant_llm_mapping.get(m["llm_name"] + "@" + m["fid"], TenantLLM(id=None)).id
            m["available"] = m["fid"] in facts or m["llm_name"].lower() == "flag-embedding" or m["fid"] in self_deployed
            if "tei-" in os.getenv("COMPOSE_PROFILES", "") and m["model_type"] == LLMType.EMBEDDING and m["fid"] == "Builtin" and m["llm_name"] == os.getenv("TEI_MODEL", ""):
                m["available"] = True
            filtered_llms.append(m)
        llms = filtered_llms

        llm_set = set([m["llm_name"] + "@" + m["fid"] for m in llms])
        for o in objs:
            if o.llm_name + "@" + o.llm_factory in llm_set:
                continue
            if o.llm_factory == "Xinference" and not _is_xinference_model_loaded(o.llm_name, xinference_loaded_model_ids):
                continue
            llms.append({"id": o.id, "llm_name": o.llm_name, "model_type": o.model_type, "fid": o.llm_factory, "available": True, "status": StatusEnum.VALID.value})

        res = {}
        for m in llms:
            if model_type and m["model_type"].find(model_type) < 0:
                continue
            if m["fid"] not in res:
                res[m["fid"]] = []
            res[m["fid"]].append(m)

        return get_json_result(data=res)
    except Exception as e:
        return server_error_response(e)
