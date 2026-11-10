import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthInput(StrictModel):
    username: str = Field(min_length=3, max_length=32)
    otp: str = Field(min_length=1, max_length=12)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str):
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9_]{3,32}", value):
            raise ValueError("Use 3–32 letters, numbers, or underscores.")
        return value


class ProfileInput(StrictModel):
    display_name: str = Field(min_length=1, max_length=64)


class ContactInput(StrictModel):
    username: str = Field(min_length=3, max_length=32)


class DirectInput(StrictModel):
    user_id: int = Field(gt=0)


class GroupInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    member_ids: list[int] = Field(min_length=1, max_length=31)


class GroupNameInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)


class MemberInput(StrictModel):
    user_id: int = Field(gt=0)


class RoleInput(StrictModel):
    role: str = Field(pattern="^(admin|member)$")


class MessageInput(StrictModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    reply_to_id: int | None = Field(default=None, gt=0)


class ReceiptInput(StrictModel):
    message_ids: list[int] = Field(min_length=1, max_length=200)
    state: str = Field(pattern="^(delivered|read)$")


class ReactionInput(StrictModel):
    emoji: str = Field(pattern="^(👍|❤️|😂|😮|😢|🙏)$")
