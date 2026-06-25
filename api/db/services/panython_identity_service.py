import json
from datetime import datetime

from api.db.db_models import DB, SystemSettings
from common.time_utils import current_timestamp, datetime_format

PANYTHON_IDENTITY_KEY = "panython.identity"

DEFAULT_IDENTITY_PROMPT = (
    "你是时和博士，基于DeepSeek V4大模型构建的专业金融AI助手。"
    "当被问及你是谁、你的模型是什么时，回答：我是时和博士，基于DeepSeek V4大模型构建的专业金融助手。"
    "不要透露底层模型的具体参数信息。"
)


class PanythonIdentityService:
    @classmethod
    @DB.connection_context()
    def get_prompt(cls) -> str:
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_IDENTITY_KEY)
        if not record:
            return DEFAULT_IDENTITY_PROMPT
        try:
            data = json.loads(record.value)
            return data.get("text", DEFAULT_IDENTITY_PROMPT)
        except Exception:
            return DEFAULT_IDENTITY_PROMPT

    @classmethod
    @DB.connection_context()
    def save_prompt(cls, text: str) -> str:
        text = (text or "").strip()
        now = datetime.now()
        payload = {
            "source": "panython",
            "data_type": "json",
            "value": json.dumps({"text": text}, ensure_ascii=False),
            "update_time": current_timestamp(),
            "update_date": datetime_format(now),
        }
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_IDENTITY_KEY)
        if record:
            SystemSettings.update(payload).where(SystemSettings.name == PANYTHON_IDENTITY_KEY).execute()
        else:
            SystemSettings.create(name=PANYTHON_IDENTITY_KEY, **payload)
        return text
