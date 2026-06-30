#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
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

import base64
import json
import logging
from datetime import datetime

import httpx
from quart import request

from api.apps import current_user, login_required
from api.db import UserTenantRole
from api.db.db_models import (
    DB,
    Dialog,
    File,
    Knowledgebase,
    Memory,
    Search,
    Tenant,
    TenantLLM,
    User,
    UserCanvas,
    UserManagementOperationLog,
    UserTenant,
)
from api.db.joint_services.tenant_model_service import get_tenant_default_model_by_type
from api.utils.api_utils import (
    get_data_error_result,
    get_json_result,
    get_request_json,
    server_error_response,
)
from api.utils.tenant_utils import ensure_tenant_model_id_for_params
from api.db.services.panython_tts_settings_service import PanythonTTSSettingsService
from api.db.services.panython_identity_service import PanythonIdentityService
from api.db.services.panython_asr_settings_service import PanythonASRSettingsService
from common.constants import LLMType, RetCode, StatusEnum
from common.misc_utils import get_uuid
from common.time_utils import current_timestamp, datetime_format

_dev_log = logging.getLogger("panython.dev")


def _require_superuser():
    if not getattr(current_user, "is_superuser", False):
        return get_json_result(
            data=False,
            message="Only superuser can manage tenant relationships.",
            code=RetCode.FORBIDDEN,
        )
    return None


def _ensure_operation_log_table():
    if not UserManagementOperationLog.table_exists():
        UserManagementOperationLog.create_table(safe=True)


def _safe_user_label(user):
    if not user:
        return ""
    return user.nickname or user.email or user.id


def _write_operation_log(action, target_type, target_id=None, target_label=None, tenant_id=None, details=None):
    try:
        _ensure_operation_log_table()
        now = datetime.now()
        timestamp = current_timestamp()
        UserManagementOperationLog.create(
            id=get_uuid(),
            operator_id=current_user.id,
            operator_label=_safe_user_label(current_user),
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            tenant_id=tenant_id,
            details=details or {},
            status=StatusEnum.VALID.value,
            create_time=timestamp,
            create_date=datetime_format(now),
            update_time=timestamp,
            update_date=datetime_format(now),
        )
    except Exception:
        import logging

        logging.exception(
            "Failed to write user management operation log: action=%s target_type=%s target_id=%s",
            action,
            target_type,
            target_id,
        )


@manager.route("/dev/tts-engine-settings", methods=["GET"])  # noqa: F821
@login_required
def get_tts_engine_settings():
    try:
        return get_json_result(data=PanythonTTSSettingsService.get_settings())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tts-engine-settings", methods=["PUT"])  # noqa: F821
@login_required
async def save_tts_engine_settings():
    denied = _require_superuser()
    if denied:
        return denied
    try:
        req = await get_request_json()
        return get_json_result(data=PanythonTTSSettingsService.save_settings(req or {}))
    except Exception as exc:
        return server_error_response(exc)


# ---------------------------------------------------------------------------
# ASR routing settings
# ---------------------------------------------------------------------------

@manager.route("/dev/asr-settings", methods=["GET"])  # noqa: F821
@login_required
def get_asr_settings():
    try:
        return get_json_result(data=PanythonASRSettingsService.get_settings())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/asr-settings", methods=["PUT"])  # noqa: F821
@login_required
async def save_asr_settings():
    denied = _require_superuser()
    if denied:
        return denied
    try:
        req = await get_request_json()
        return get_json_result(data=PanythonASRSettingsService.save_settings(req or {}))
    except Exception as exc:
        return server_error_response(exc)


# ---------------------------------------------------------------------------
# TTS voice profiles (Custom voice cloning — Part 2)
# ---------------------------------------------------------------------------

def _get_tts_base_url() -> str | None:
    """Return the CosyVoice3 server base URL from the admin tenant's TTS model config."""
    try:
        engine_settings = PanythonTTSSettingsService.get_settings()
        if not engine_settings.get("tts_enabled"):
            return None
        # Try to get the TTS model config from the current user's tenant.
        model_config = get_tenant_default_model_by_type(current_user.id, LLMType.TTS)
        if not model_config:
            return None
        base_url = (model_config.get("api_base") or "").rstrip("/")
        return base_url if base_url else None
    except Exception as exc:
        _dev_log.warning("Could not resolve TTS base URL: %s", exc)
        return None


@manager.route("/dev/tts-voices", methods=["GET"])  # noqa: F821
@login_required
async def list_tts_voices():
    try:
        base_url = _get_tts_base_url()
        if not base_url:
            return get_data_error_result(message="TTS engine not configured or disabled.")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/v1/voices")
            resp.raise_for_status()
        return get_json_result(data=resp.json())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tts-voices", methods=["POST"])  # noqa: F821
@login_required
async def add_tts_voice():
    try:
        base_url = _get_tts_base_url()
        if not base_url:
            return get_data_error_result(message="TTS engine not configured or disabled.")

        form = await request.form
        files = await request.files

        voice_id = (form.get("voice_id") or "").strip()
        display_name = (form.get("display_name") or "").strip()
        prompt_text = (form.get("prompt_text") or "").strip()

        if not voice_id:
            return get_data_error_result(message="voice_id is required.")
        if not prompt_text:
            return get_data_error_result(message="prompt_text is required.")

        audio_file = files.get("audio")
        if not audio_file:
            return get_data_error_result(message="audio file is required.")

        audio_data = audio_file.read()
        if not audio_data:
            return get_data_error_result(message="audio file is empty.")

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        payload = {
            "voice_id": voice_id,
            "display_name": display_name or voice_id,
            "prompt_text": prompt_text,
            "audio_base64": audio_b64,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{base_url}/v1/voices/add", json=payload)
            if resp.status_code != 200:
                error_detail = resp.json().get("detail", resp.text) if resp.content else resp.text
                return get_data_error_result(message=f"CosyVoice3 error: {error_detail}")
        return get_json_result(data=resp.json())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tts-voices/<voice_id>", methods=["DELETE"])  # noqa: F821
@login_required
async def delete_tts_voice(voice_id: str):
    try:
        base_url = _get_tts_base_url()
        if not base_url:
            return get_data_error_result(message="TTS engine not configured or disabled.")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(f"{base_url}/v1/voices/{voice_id}")
            if resp.status_code not in (200, 404):
                error_detail = resp.json().get("detail", resp.text) if resp.content else resp.text
                return get_data_error_result(message=f"CosyVoice3 error: {error_detail}")
        return get_json_result(data=resp.json())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/ds4-health", methods=["GET"])  # noqa: F821
@login_required
def get_ds4_health():
    try:
        import json as _json
        from pathlib import Path as _Path
        health_file = _Path("/home/xsuper/app/newapp/runtime/ds4/ds4-health.json")
        if health_file.exists():
            return get_json_result(data=_json.loads(health_file.read_text(encoding="utf-8")))
        return get_json_result(
            data={
                "state": "unknown",
                "ready": False,
                "blocking": False,
                "usage_percent": None,
                "restart_usage_percent": None,
                "maintenance_progress": None,
                "maintenance_phase": None,
            }
        )
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/identity", methods=["GET"])  # noqa: F821
@login_required
def get_identity():
    try:
        return get_json_result(data={"text": PanythonIdentityService.get_prompt()})
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/identity", methods=["POST"])  # noqa: F821
@login_required
def save_identity():
    try:
        body = request.json or {}
        text = PanythonIdentityService.save_prompt(body.get("text", ""))
        return get_json_result(data={"text": text})
    except Exception as exc:
        return server_error_response(exc)


def _user_label(users_by_id, user_id):
    user = users_by_id.get(user_id)
    if not user:
        return ""
    return user.get("nickname") or user.get("email") or user_id


def _asset_counts(tenant_id):
    status = StatusEnum.VALID.value
    return {
        "members": UserTenant.select().where(
            UserTenant.tenant_id == tenant_id,
            UserTenant.user_id != tenant_id,
            UserTenant.status == status,
        ).count(),
        "datasets": Knowledgebase.select().where(Knowledgebase.tenant_id == tenant_id, Knowledgebase.status == status).count(),
        "dialogs": Dialog.select().where(Dialog.tenant_id == tenant_id, Dialog.status == status).count(),
        "searches": Search.select().where(Search.tenant_id == tenant_id, Search.status == status).count(),
        "agents": UserCanvas.select().where(UserCanvas.user_id == tenant_id).count(),
        "memories": Memory.select().where(Memory.tenant_id == tenant_id).count(),
        "models": TenantLLM.select().where(TenantLLM.tenant_id == tenant_id, TenantLLM.status == status).count(),
    }


def _delete_blockers(relation, counts):
    if relation["status"] != StatusEnum.VALID.value:
        return []
    is_owner_relation = relation["role"] == UserTenantRole.OWNER.value or relation["user_id"] == relation["tenant_id"]
    if not is_owner_relation:
        return []
    blockers = [f"{key}:{value}" for key, value in counts.items() if value]
    return blockers


def _user_delete_blockers(user_id):
    status = StatusEnum.VALID.value
    blockers = []
    owned_counts = _asset_counts(user_id)
    for key in ("members", "datasets", "dialogs", "searches", "agents", "memories"):
        value = owned_counts.get(key, 0)
        if value:
            blockers.append(f"{key}:{value}")
    return blockers


def _relationship_payload():
    users = list(
        User.select(
            User.id,
            User.email,
            User.nickname,
            User.is_superuser,
            User.status,
            User.update_time,
        )
        .where(User.status == StatusEnum.VALID.value)
        .order_by(User.update_time.desc())
        .dicts()
    )
    users_by_id = {user["id"]: user for user in users}

    memberships = list(
        UserTenant.select(
            UserTenant.id,
            UserTenant.user_id,
            UserTenant.tenant_id,
            UserTenant.role,
            UserTenant.status,
            UserTenant.invited_by,
            UserTenant.update_time,
        )
        .where(UserTenant.status == StatusEnum.VALID.value)
        .order_by(UserTenant.update_time.desc())
        .dicts()
    )
    memberships = [
        item
        for item in memberships
        if item["user_id"] in users_by_id and item["tenant_id"] in users_by_id
    ]

    tenant_ids = {item["tenant_id"] for item in memberships}
    tenant_ids.update({user["id"] for user in users})
    counts_by_tenant = {
        tenant_id: _asset_counts(tenant_id) for tenant_id in tenant_ids
    }

    for item in memberships:
        item["user_label"] = _user_label(users_by_id, item["user_id"])
        item["tenant_label"] = _user_label(users_by_id, item["tenant_id"])
        item["asset_counts"] = counts_by_tenant.get(item["tenant_id"], {})
        item["delete_blockers"] = _delete_blockers(item, item["asset_counts"])
        item["can_delete"] = not item["delete_blockers"]

    dialogs = list(
        Dialog.select(
            Dialog.id,
            Dialog.tenant_id,
            Dialog.name,
            Dialog.description,
            Dialog.llm_id,
            Dialog.tenant_llm_id,
            Dialog.rerank_id,
            Dialog.tenant_rerank_id,
            Dialog.kb_ids,
            Dialog.status,
            Dialog.update_time,
        )
        .where(Dialog.status == StatusEnum.VALID.value)
        .order_by(Dialog.update_time.desc())
        .dicts()
    )
    dialogs = [dialog for dialog in dialogs if dialog["tenant_id"] in users_by_id]
    knowledgebases = list(
        Knowledgebase.select(
            Knowledgebase.id,
            Knowledgebase.tenant_id,
            Knowledgebase.name,
            Knowledgebase.permission,
            Knowledgebase.doc_num,
            Knowledgebase.chunk_num,
            Knowledgebase.token_num,
            Knowledgebase.status,
            Knowledgebase.update_time,
        )
        .where(Knowledgebase.status == StatusEnum.VALID.value)
        .order_by(Knowledgebase.update_time.desc())
        .dicts()
    )
    knowledgebases = [kb for kb in knowledgebases if kb["tenant_id"] in users_by_id]
    kb_by_id = {kb["id"]: kb for kb in knowledgebases}
    for dialog in dialogs:
        dialog["tenant_label"] = _user_label(users_by_id, dialog["tenant_id"])
        dialog["kb_ids"] = dialog.get("kb_ids") or []
        dialog["kb_names"] = [
            kb_by_id[kb_id]["name"]
            for kb_id in dialog["kb_ids"]
            if kb_id in kb_by_id
        ]
    for kb in knowledgebases:
        kb["tenant_label"] = _user_label(users_by_id, kb["tenant_id"])

    return {
        "current_user_id": current_user.id,
        "users": users,
        "memberships": memberships,
        "dialogs": dialogs,
        "knowledgebases": knowledgebases,
        "asset_counts": counts_by_tenant,
    }


@manager.route("/dev/tenant-relations", methods=["GET"])  # noqa: F821
@login_required
def list_tenant_relations():
    denied = _require_superuser()
    if denied:
        return denied
    try:
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/users/<user_id>", methods=["DELETE"])  # noqa: F821
@login_required
def delete_user(user_id):
    denied = _require_superuser()
    if denied:
        return denied
    try:
        user = User.get_or_none(User.id == user_id)
        has_residual_rows = (
            UserTenant.select()
            .where((UserTenant.user_id == user_id) | (UserTenant.tenant_id == user_id))
            .exists()
            or Tenant.get_or_none(Tenant.id == user_id) is not None
            or TenantLLM.select().where(TenantLLM.tenant_id == user_id).exists()
        )
        if not user and not has_residual_rows:
            return get_data_error_result(message="User not found.")
        if user_id == current_user.id:
            return get_json_result(
                data=False,
                message="The current login user cannot be deleted.",
                code=RetCode.OPERATING_ERROR,
            )
        blockers = _user_delete_blockers(user_id)
        if blockers:
            return get_json_result(
                data={"blockers": blockers},
                message="The user still has group relationships or dependent resources. Remove or transfer them first.",
                code=RetCode.OPERATING_ERROR,
            )

        before = user.to_safe_dict() if user else {"id": user_id, "missing_user": True}
        now = datetime.now()
        timestamp = current_timestamp()
        with DB.atomic():
            if user:
                User.update(
                    {
                        "status": StatusEnum.INVALID.value,
                        "update_time": timestamp,
                        "update_date": datetime_format(now),
                    }
                ).where(User.id == user_id).execute()
            Tenant.update(
                {
                    "status": StatusEnum.INVALID.value,
                    "update_time": timestamp,
                    "update_date": datetime_format(now),
                }
            ).where(Tenant.id == user_id).execute()
            UserTenant.update(
                {
                    "status": StatusEnum.INVALID.value,
                    "update_time": timestamp,
                    "update_date": datetime_format(now),
                }
            ).where(
                ((UserTenant.user_id == user_id) | (UserTenant.tenant_id == user_id)),
                UserTenant.status == StatusEnum.VALID.value,
            ).execute()
            TenantLLM.update(
                {
                    "status": StatusEnum.INVALID.value,
                    "update_time": timestamp,
                    "update_date": datetime_format(now),
                }
            ).where(
                TenantLLM.tenant_id == user_id,
                TenantLLM.status == StatusEnum.VALID.value,
            ).execute()
            File.delete().where(
                (File.tenant_id == user_id) | (File.created_by == user_id)
            ).execute()
            _write_operation_log(
                "user_delete",
                "user",
                user_id,
                target_label=_safe_user_label(user) if user else user_id,
                tenant_id=user_id,
                details={"before": before},
            )
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations", methods=["POST"])  # noqa: F821
@login_required
async def upsert_tenant_relation():
    denied = _require_superuser()
    if denied:
        return denied
    try:
        req = await get_request_json()
        user_id = (req.get("user_id") or "").strip()
        tenant_id = (req.get("tenant_id") or "").strip()
        role = (req.get("role") or UserTenantRole.NORMAL.value).strip()

        if role not in {
            UserTenantRole.OWNER.value,
            UserTenantRole.ADMIN.value,
            UserTenantRole.NORMAL.value,
        }:
            return get_data_error_result(message="Invalid role.")
        if not User.get_or_none(
            User.id == user_id,
            User.status == StatusEnum.VALID.value,
        ):
            return get_data_error_result(message="User not found.")
        if not User.get_or_none(
            User.id == tenant_id,
            User.status == StatusEnum.VALID.value,
        ):
            return get_data_error_result(message="Tenant not found.")

        user = User.get_or_none(User.id == user_id)
        tenant = User.get_or_none(User.id == tenant_id)
        target_label = f"{_safe_user_label(user)} -> {_safe_user_label(tenant)}"
        now = datetime.now()
        relation = UserTenant.get_or_none(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == tenant_id,
        )
        with DB.atomic():
            if relation:
                old_snapshot = relation.to_dict()
                relation.role = role
                relation.status = StatusEnum.VALID.value
                relation.invited_by = current_user.id
                relation.update_time = current_timestamp()
                relation.update_date = datetime_format(now)
                relation.save()
                relation_id = relation.id
                action = "user_group_membership_update"
            else:
                relation = UserTenant.create(
                    id=get_uuid(),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=role,
                    invited_by=current_user.id,
                    status=StatusEnum.VALID.value,
                )
                old_snapshot = None
                relation_id = relation.id
                action = "user_group_membership_create"
            _write_operation_log(
                action,
                "user_group_membership",
                relation_id,
                target_label=target_label,
                tenant_id=tenant_id,
                details={
                    "before": old_snapshot,
                    "after": {"user_id": user_id, "tenant_id": tenant_id, "role": role},
                },
            )

        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations/<relation_id>", methods=["DELETE"])  # noqa: F821
@login_required
def delete_tenant_relation(relation_id):
    denied = _require_superuser()
    if denied:
        return denied
    try:
        relation_obj = UserTenant.get_or_none(UserTenant.id == relation_id)
        if not relation_obj:
            return get_data_error_result(message="Relationship not found.")
        relation = relation_obj.to_dict()
        counts = _asset_counts(relation["tenant_id"])
        blockers = _delete_blockers(relation, counts)
        if blockers:
            return get_json_result(
                data={"blockers": blockers},
                message="The tenant still has dependent resources. Remove or transfer them first.",
                code=RetCode.OPERATING_ERROR,
            )

        is_owner_relation = (
            relation["role"] == UserTenantRole.OWNER.value
            or relation["user_id"] == relation["tenant_id"]
        )
        relation_obj.status = StatusEnum.INVALID.value
        relation_obj.update_time = current_timestamp()
        relation_obj.update_date = datetime_format(datetime.now())
        relation_obj.save()
        _write_operation_log(
            "user_group_delete" if is_owner_relation else "user_group_membership_delete",
            "user_group" if is_owner_relation else "user_group_membership",
            relation_id,
            target_label=f"{relation.get('user_id')} -> {relation.get('tenant_id')}",
            tenant_id=relation["tenant_id"],
            details={"before": relation, "asset_counts": counts},
        )
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations/dialogs/<dialog_id>/tenant", methods=["PUT"])  # noqa: F821
@login_required
async def transfer_dialog_tenant(dialog_id):
    denied = _require_superuser()
    if denied:
        return denied
    try:
        req = await get_request_json()
        tenant_id = (req.get("tenant_id") or "").strip()
        if not User.get_or_none(
            User.id == tenant_id,
            User.status == StatusEnum.VALID.value,
        ):
            return get_data_error_result(message="Tenant not found.")

        dialog = Dialog.get_or_none(
            Dialog.id == dialog_id,
            Dialog.status == StatusEnum.VALID.value,
        )
        if not dialog:
            return get_data_error_result(message="Dialog not found.")

        model_params = ensure_tenant_model_id_for_params(
            tenant_id,
            {
                "llm_id": dialog.llm_id,
                "rerank_id": dialog.rerank_id,
            },
        )
        update_data = {
            "tenant_id": tenant_id,
            "tenant_llm_id": model_params.get("tenant_llm_id") or None,
            "tenant_rerank_id": model_params.get("tenant_rerank_id") or None,
            "update_time": current_timestamp(),
            "update_date": datetime_format(datetime.now()),
        }
        Dialog.update(update_data).where(Dialog.id == dialog_id).execute()
        _write_operation_log(
            "chat_assistant_group_change",
            "chat_assistant",
            dialog_id,
            target_label=dialog.name,
            tenant_id=tenant_id,
            details={
                "before": {"tenant_id": dialog.tenant_id},
                "after": {"tenant_id": tenant_id},
            },
        )
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations/dialogs/<dialog_id>/knowledgebases", methods=["PUT"])  # noqa: F821
@login_required
async def update_dialog_knowledgebases(dialog_id):
    denied = _require_superuser()
    if denied:
        return denied
    try:
        req = await get_request_json()
        kb_ids = req.get("kb_ids") or []
        if not isinstance(kb_ids, list):
            return get_data_error_result(message="kb_ids must be a list.")
        kb_ids = list(
            dict.fromkeys(
                str(kb_id).strip()
                for kb_id in kb_ids
                if str(kb_id).strip()
            )
        )

        dialog = Dialog.get_or_none(
            Dialog.id == dialog_id,
            Dialog.status == StatusEnum.VALID.value,
        )
        if not dialog:
            return get_data_error_result(message="Dialog not found.")

        if kb_ids:
            valid_kbs = list(
                Knowledgebase.select(Knowledgebase.id, Knowledgebase.tenant_id)
                .where(
                    Knowledgebase.id.in_(kb_ids),
                    Knowledgebase.status == StatusEnum.VALID.value,
                )
                .dicts()
            )
            valid_ids = {kb["id"] for kb in valid_kbs}
            missing_ids = [kb_id for kb_id in kb_ids if kb_id not in valid_ids]
            if missing_ids:
                return get_data_error_result(
                    message=f"Knowledgebase not found: {', '.join(missing_ids)}"
                )
        Dialog.update(
            {
                "kb_ids": kb_ids,
                "update_time": current_timestamp(),
                "update_date": datetime_format(datetime.now()),
            }
        ).where(Dialog.id == dialog_id).execute()
        _write_operation_log(
            "chat_assistant_knowledgebases_update",
            "chat_assistant",
            dialog_id,
            target_label=dialog.name,
            tenant_id=dialog.tenant_id,
            details={
                "before": {"kb_ids": dialog.kb_ids or []},
                "after": {"kb_ids": kb_ids},
            },
        )
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations/dialogs/<dialog_id>", methods=["DELETE"])  # noqa: F821
@login_required
def delete_dialog(dialog_id):
    denied = _require_superuser()
    if denied:
        return denied
    try:
        dialog = Dialog.get_or_none(
            Dialog.id == dialog_id,
            Dialog.status == StatusEnum.VALID.value,
        )
        if not dialog:
            return get_data_error_result(message="Dialog not found.")
        before = dialog.to_dict()
        Dialog.update(
            {
                "status": StatusEnum.INVALID.value,
                "update_time": current_timestamp(),
                "update_date": datetime_format(datetime.now()),
            }
        ).where(Dialog.id == dialog_id).execute()
        _write_operation_log(
            "chat_assistant_delete",
            "chat_assistant",
            dialog_id,
            target_label=dialog.name,
            tenant_id=dialog.tenant_id,
            details={"before": before},
        )
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/dev/tenant-relations/logs", methods=["GET"])  # noqa: F821
@login_required
def list_operation_logs():
    denied = _require_superuser()
    if denied:
        return denied
    try:
        _ensure_operation_log_table()
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 50)), 1), 200)
        query = UserManagementOperationLog.select().where(
            UserManagementOperationLog.status == StatusEnum.VALID.value
        )
        total = query.count()
        logs = list(
            query.order_by(UserManagementOperationLog.create_time.desc())
            .paginate(page, page_size)
            .dicts()
        )
        return get_json_result(data={"logs": logs, "total": total})
    except Exception as exc:
        return server_error_response(exc)
