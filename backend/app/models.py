from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(64))
    avatar: Mapped[str | None] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(16), default="blue")
    created_at: Mapped[str] = mapped_column(String(32))
    last_seen: Mapped[str] = mapped_column(String(32))


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[str] = mapped_column(String(32), index=True)


class Contact(Base):
    __tablename__ = "contacts"
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (CheckConstraint("owner_id != contact_id", name="contact_not_self"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str | None] = mapped_column(String(80))
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    direct_key: Mapped[str | None] = mapped_column(String(50), unique=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    __table_args__ = (
        CheckConstraint("kind IN ('direct','group')", name="conversation_kind"),
        CheckConstraint("(kind = 'direct' AND direct_key IS NOT NULL) OR (kind = 'group' AND direct_key IS NULL)", name="direct_key_required"),
    )


class Member(Base):
    __tablename__ = "conversation_members"
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(8), default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[str] = mapped_column(String(32))
    left_at: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        CheckConstraint("role IN ('admin','member')", name="member_role"),
        Index("ix_members_user_active", "user_id", "active"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    client_message_id: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    __table_args__ = (
        UniqueConstraint("sender_id", "client_message_id", name="uq_message_retry"),
        Index("ix_message_history", "conversation_id", "id"),
        CheckConstraint("length(body) BETWEEN 1 AND 4000", name="message_length"),
        {"sqlite_autoincrement": True},
    )


class Recipient(Base):
    __tablename__ = "message_recipients"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    delivered_at: Mapped[str | None] = mapped_column(String(32))
    read_at: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        Index("ix_recipients_unread", "user_id", "read_at", "message_id"),
        Index("ix_recipients_delivery", "user_id", "delivered_at", "message_id"),
        CheckConstraint("read_at IS NULL OR delivered_at IS NOT NULL", name="read_implies_delivered"),
    )


class Reaction(Base):
    __tablename__ = "reactions"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    emoji: Mapped[str] = mapped_column(String(16))
