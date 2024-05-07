import dataclasses
from typing import Optional


@dataclasses.dataclass
class ContactInfo:
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    slack_channel_id: Optional[str] = None


@dataclasses.dataclass
class Publisher:
    key: str
    name: str
    contact_info: Optional[ContactInfo] = None
