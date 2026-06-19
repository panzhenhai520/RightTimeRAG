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

from datetime import datetime

from api.apps import current_user, login_required
from api.db import UserTenantRole
from api.db.db_models import (
    DB,
    Dialog,
    Knowledgebase,
    Memory,
    Search,
    TenantLLM,
    User,
    UserCanvas,
    UserTenant,
)
from api.utils.api_utils import (
    get_data_error_result,
    get_json_result,
    get_request_json,
    server_error_response,
)
from api.utils.tenant_utils import ensure_tenant_model_id_for_params
from api.db.services.panython_tts_settings_service import PanythonTTSSettingsService
from common.constants import RetCode, StatusEnum
from common.misc_utils import get_uuid
from common.time_utils import current_timestamp, datetime_format


def _require_superuser():
    if not getattr(current_user, "is_superuser", False):
        return get_json_result(
            data=False,
            message="Only superuser can manage tenant relationships.",
            code=RetCode.FORBIDDEN,
        )
    return None


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


def _user_label(users_by_id, user_id):
    user = users_by_id.get(user_id)
    if not user:
        return user_id
    return user.get("nickname") or user.get("email") or user_id


def _asset_counts(tenant_id):
    status = StatusEnum.VALID.value
    return {
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
        .order_by(UserTenant.update_time.desc())
        .dicts()
    )

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

        now = datetime.now()
        relation = UserTenant.get_or_none(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == tenant_id,
        )
        with DB.atomic():
            if relation:
                relation.role = role
                relation.status = StatusEnum.VALID.value
                relation.invited_by = current_user.id
                relation.update_time = current_timestamp()
                relation.update_date = datetime_format(now)
                relation.save()
            else:
                UserTenant.create(
                    id=get_uuid(),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=role,
                    invited_by=current_user.id,
                    status=StatusEnum.VALID.value,
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

        relation_obj.status = StatusEnum.INVALID.value
        relation_obj.update_time = current_timestamp()
        relation_obj.update_date = datetime_format(datetime.now())
        relation_obj.save()
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
            foreign_ids = [
                kb["id"]
                for kb in valid_kbs
                if kb["tenant_id"] != dialog.tenant_id
            ]
            if foreign_ids:
                return get_data_error_result(
                    message="Knowledgebase must belong to the same tenant as the dialog."
                )

        Dialog.update(
            {
                "kb_ids": kb_ids,
                "update_time": current_timestamp(),
                "update_date": datetime_format(datetime.now()),
            }
        ).where(Dialog.id == dialog_id).execute()
        return get_json_result(data=_relationship_payload())
    except Exception as exc:
        return server_error_response(exc)
