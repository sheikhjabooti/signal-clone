"""All persistent application rules live here. Each operation owns its DB session.

These synchronous functions run in FastAPI's thread pool. WebSocket code never
holds a database session while waiting for the network.
"""
from collections import Counter, defaultdict
import secrets
from sqlalchemy import delete, exists, func, or_, select
from .config import Settings
from .database import Database
from .models import Contact, Conversation, Member, Message, Reaction, Recipient, SessionToken, User
from .schemas import AuthInput, GroupInput, MessageInput
from .security import AppError, Identity, digest, expires_in, now, random_token


def user_json(user: User):
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "avatar_url": f"/api/avatars/{user.avatar}" if user.avatar else None,
            "color": user.color, "last_seen": user.last_seen}


def visible_to(uid: int):
    return or_(Message.sender_id == uid, exists().where(
        Recipient.message_id == Message.id, Recipient.user_id == uid))


def active_users(session, cid: int) -> list[int]:
    return list(session.scalars(select(Member.user_id).where(
        Member.conversation_id == cid, Member.active.is_(True))))


def require_member(session, cid: int, uid: int, admin: bool = False):
    membership = session.get(Member, (cid, uid))
    if not membership or not membership.active:
        raise AppError(403, "not_a_member", "You no longer have access to this conversation.")
    if admin and membership.role != "admin":
        raise AppError(403, "admin_required", "Only a group admin can do that.")
    return membership


def require_group(session, cid: int, uid: int):
    member = require_member(session, cid, uid, admin=True)
    conversation = session.get(Conversation, cid)
    if conversation.kind != "group":
        raise AppError(400, "not_a_group", "This action is only available in groups.")
    return member, conversation


def require_visible_message(session, mid: int, uid: int):
    message = session.scalar(select(Message).where(Message.id == mid, visible_to(uid)))
    if not message:
        raise AppError(404, "message_not_found", "That message is not available.")
    require_member(session, message.conversation_id, uid)
    return message


def messages_json(session, items: list[Message], uid: int):
    """Batch receipts/reactions/users instead of issuing a query per bubble."""
    if not items:
        return []
    ids = [m.id for m in items]
    receipts: dict[int, list[Recipient]] = defaultdict(list)
    reactions: dict[int, list[Reaction]] = defaultdict(list)
    for row in session.scalars(select(Recipient).where(Recipient.message_id.in_(ids))):
        receipts[row.message_id].append(row)
    for row in session.scalars(select(Reaction).where(Reaction.message_id.in_(ids))):
        reactions[row.message_id].append(row)
    reply_ids = {m.reply_to_id for m in items if m.reply_to_id}
    replies = {m.id: m for m in session.scalars(select(Message).where(
        Message.id.in_(reply_ids), visible_to(uid)))} if reply_ids else {}
    user_ids = {m.sender_id for m in items} | {m.sender_id for m in replies.values()}
    people = {u.id: user_json(u) for u in session.scalars(select(User).where(User.id.in_(user_ids)))}
    output = []
    for message in items:
        rows = receipts[message.id]
        mine = next((r for r in rows if r.user_id == uid), None)
        delivered = sum(r.delivered_at is not None for r in rows)
        read = sum(r.read_at is not None for r in rows)
        status = "read" if rows and read == len(rows) else "delivered" if rows and delivered == len(rows) else "sent"
        counts = Counter(r.emoji for r in reactions[message.id])
        my_reaction = next((r.emoji for r in reactions[message.id] if r.user_id == uid), None)
        reply = replies.get(message.reply_to_id)
        output.append({
            "id": message.id, "conversation_id": message.conversation_id,
            "client_message_id": message.client_message_id, "body": message.body,
            "sender_id": message.sender_id, "sender": people[message.sender_id],
            "created_at": message.created_at, "status": status,
            "recipient_count": len(rows), "delivered_count": delivered, "read_count": read,
            "delivered_at": mine.delivered_at if mine else None, "read_at": mine.read_at if mine else None,
            "reply_to_id": message.reply_to_id,
            "reply": {"id": reply.id, "body": reply.body, "sender_name": people[reply.sender_id]["display_name"]} if reply else None,
            "reactions": [{"emoji": emoji, "count": count, "mine": my_reaction == emoji} for emoji, count in counts.items()],
        })
    return output


class Services:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def authenticate(self, data: AuthInput, register: bool):
        if not secrets.compare_digest(data.otp, self.settings.demo_otp):
            raise AppError(401, "wrong_code", "That code did not match. Use the demo code shown below.")
        with self.db.write() as session:
            user = session.scalar(select(User).where(User.username == data.username))
            if register:
                if user:
                    raise AppError(409, "username_taken", "That username is already taken. Try signing in instead.")
                user = User(username=data.username, display_name=data.display_name or data.username,
                            created_at=now(), last_seen=now(), color=secrets.choice(["blue", "teal", "pink", "purple", "orange"]))
                session.add(user)
                session.flush()
            elif not user:
                raise AppError(404, "user_not_found", "No account with that username. You can create one below.")
            session.execute(delete(SessionToken).where(SessionToken.expires_at < now()))
            token, csrf = random_token(), random_token()
            record = SessionToken(token_hash=digest(token), user_id=user.id, csrf_token=csrf,
                                  expires_at=expires_in(self.settings.session_days))
            session.add(record)
            result = {"user": user_json(user), "csrf_token": csrf}
        return result, token

    def identity(self, token: str | None) -> Identity:
        if not token:
            raise AppError(401, "unauthenticated", "Please sign in to continue.")
        return self.identity_hash(digest(token))

    def identity_hash(self, token_hash: str) -> Identity:
        with self.db.read() as session:
            record = session.get(SessionToken, token_hash)
            if not record or record.expires_at <= now():
                raise AppError(401, "session_expired", "Your session ended. Please sign in again.")
            return Identity(record.user_id, record.token_hash, record.csrf_token, record.expires_at)

    def me(self, identity: Identity):
        with self.db.read() as session:
            return {"user": user_json(session.get(User, identity.user_id)), "csrf_token": identity.csrf_token}

    def logout(self, identity: Identity):
        with self.db.write() as session:
            session.execute(delete(SessionToken).where(SessionToken.token_hash == identity.token_hash))

    def profile(self, uid: int, display_name: str | None = None, avatar: str | None = None):
        with self.db.write() as session:
            user = session.get(User, uid)
            if display_name is not None:
                user.display_name = display_name
            if avatar is not None:
                user.avatar = avatar
            return user_json(user)

    def last_seen(self, uid: int):
        with self.db.write() as session:
            user = session.get(User, uid)
            if user:
                user.last_seen = now()

    def list_contacts(self, uid: int):
        with self.db.read() as session:
            return [user_json(u) for u in session.scalars(select(User).join(Contact, Contact.contact_id == User.id)
                    .where(Contact.owner_id == uid).order_by(User.display_name))]

    def search_users(self, uid: int, query: str):
        if len(query.strip()) < 2:
            return []
        with self.db.read() as session:
            return [user_json(u) for u in session.scalars(select(User).where(User.id != uid, or_(
                User.username.contains(query.lower(), autoescape=True),
                func.lower(User.display_name).contains(query.lower(), autoescape=True)
            )).order_by(User.display_name).limit(30))]

    def add_contact(self, uid: int, username: str):
        with self.db.write() as session:
            user = session.scalar(select(User).where(User.username == username.strip().lower()))
            if not user:
                raise AppError(404, "user_not_found", "No account with that username.")
            if user.id == uid:
                raise AppError(400, "self_contact", "You cannot add yourself as a contact.")
            if not session.get(Contact, (uid, user.id)):
                session.add(Contact(owner_id=uid, contact_id=user.id))
            return user_json(user)

    def summary(self, session, conversation: Conversation, uid: int):
        require_member(session, conversation.id, uid)
        people = list(session.execute(select(Member, User).join(User, User.id == Member.user_id).where(
            Member.conversation_id == conversation.id, Member.active.is_(True))))
        members = [{**user_json(user), "role": member.role} for member, user in people]
        other = next((u for u in members if u["id"] != uid), None)
        latest = session.scalar(select(Message).where(Message.conversation_id == conversation.id, visible_to(uid))
                                .order_by(Message.id.desc()).limit(1))
        unread = session.scalar(select(func.count()).select_from(Recipient).join(Message).where(
            Message.conversation_id == conversation.id, Recipient.user_id == uid, Recipient.read_at.is_(None)))
        return {"id": conversation.id, "kind": conversation.kind,
                "name": conversation.name if conversation.kind == "group" else (other or {}).get("display_name", "Conversation"),
                "members": members, "peer": other if conversation.kind == "direct" else None,
                "role": next(u["role"] for u in members if u["id"] == uid), "unread_count": unread,
                "created_at": conversation.created_at,
                "updated_at": latest.created_at if latest else conversation.created_at,
                "last_message": messages_json(session, [latest], uid)[0] if latest else None}

    def conversations(self, uid: int, query: str = ""):
        with self.db.read() as session:
            records = session.scalars(select(Conversation).join(Member).where(Member.user_id == uid, Member.active.is_(True)))
            result = [self.summary(session, c, uid) for c in records]
        if query:
            q = query.lower()
            result = [c for c in result if q in c["name"].lower() or any(q in m["username"] for m in c["members"])]
        return sorted(result, key=lambda c: c["updated_at"], reverse=True)

    def conversation(self, uid: int, cid: int):
        with self.db.read() as session:
            require_member(session, cid, uid)
            return self.summary(session, session.get(Conversation, cid), uid)

    def direct(self, uid: int, other_id: int):
        if uid == other_id:
            raise AppError(400, "self_chat", "Pick another person to start a conversation.")
        key = ":".join(map(str, sorted([uid, other_id])))
        with self.db.write() as session:
            if not session.get(User, other_id):
                raise AppError(404, "user_not_found", "That person is not available.")
            conversation = session.scalar(select(Conversation).where(Conversation.direct_key == key))
            if not conversation:
                conversation = Conversation(kind="direct", direct_key=key, creator_id=uid, created_at=now(), updated_at=now())
                session.add(conversation)
                session.flush()
                for user_id in [uid, other_id]:
                    session.add(Member(conversation_id=conversation.id, user_id=user_id, role="member", active=True, joined_at=now()))
                session.flush()
            result = self.summary(session, conversation, uid)
        return result, [uid, other_id]

    def group(self, uid: int, data: GroupInput):
        ids = sorted(set(data.member_ids) | {uid})
        if not 2 <= len(ids) <= self.settings.max_group_size:
            raise AppError(400, "group_size", "A group needs between 2 and 32 people.")
        with self.db.write() as session:
            if session.scalar(select(func.count()).select_from(User).where(User.id.in_(ids))) != len(ids):
                raise AppError(404, "user_not_found", "One of those people no longer exists.")
            conversation = Conversation(kind="group", name=data.name, creator_id=uid, created_at=now(), updated_at=now())
            session.add(conversation)
            session.flush()
            for user_id in ids:
                session.add(Member(conversation_id=conversation.id, user_id=user_id,
                                   role="admin" if user_id == uid else "member", active=True, joined_at=now()))
            session.flush()
            result = self.summary(session, conversation, uid)
        return result, ids

    def rename_group(self, uid: int, cid: int, name: str):
        with self.db.write() as session:
            _, group = require_group(session, cid, uid)
            group.name, group.updated_at = name, now()
            audience = active_users(session, cid)
        return audience

    def change_member(self, uid: int, cid: int, target: int, action: str, role: str = "member"):
        with self.db.write() as session:
            require_group(session, cid, uid)
            audience = active_users(session, cid)
            member = session.get(Member, (cid, target))
            if action == "add":
                if not session.get(User, target):
                    raise AppError(404, "user_not_found", "That person is not available.")
                if member and member.active:
                    return audience
                if len(audience) >= self.settings.max_group_size:
                    raise AppError(400, "group_size", "This demo supports up to 32 people in a group.")
                if member:
                    member.active, member.left_at, member.joined_at, member.role = True, None, now(), "member"
                else:
                    session.add(Member(conversation_id=cid, user_id=target, role="member", active=True, joined_at=now()))
            else:
                if not member or not member.active:
                    raise AppError(404, "member_not_found", "That person is not in the group.")
                if member.role == "admin" and (action == "remove" or role == "member"):
                    count = session.scalar(select(func.count()).select_from(Member).where(
                        Member.conversation_id == cid, Member.active.is_(True), Member.role == "admin"))
                    if count <= 1:
                        raise AppError(409, "last_admin", "Make someone else an admin first.")
                if action == "remove":
                    member.active, member.left_at = False, now()
                elif action == "role":
                    member.role = role
            return list(set(audience + [target]))

    def history(self, uid: int, cid: int, limit: int = 50, before_id: int | None = None,
                after_id: int | None = None, through_id: int | None = None):
        if before_id is not None and after_id is not None:
            raise AppError(400, "bad_cursor", "Use either an older-page cursor or a catch-up cursor.")
        with self.db.read() as session:
            require_member(session, cid, uid)
            base = select(Message).where(Message.conversation_id == cid, visible_to(uid))
            high = session.scalar(select(func.max(Message.id)).where(Message.conversation_id == cid, visible_to(uid))) or 0
            through = min(through_id, high) if through_id is not None else high
            query = base.where(Message.id <= through)
            if before_id is not None:
                query = query.where(Message.id < before_id)
            if after_id is not None:
                query = query.where(Message.id > after_id).order_by(Message.id.asc())
            else:
                query = query.order_by(Message.id.desc())
            records = list(session.scalars(query.limit(limit + 1)))
            has_more = len(records) > limit
            records = records[:limit]
            if after_id is None:
                records.reverse()
            return {"messages": messages_json(session, records, uid), "has_more": has_more,
                    "through_id": through,
                    "next_after_id": records[-1].id if records else (after_id or through),
                    "next_before_id": records[0].id if records else None}

    def send(self, uid: int, cid: int, data: MessageInput):
        with self.db.write() as session:
            require_member(session, cid, uid)
            existing = session.scalar(select(Message).where(Message.sender_id == uid, Message.client_message_id == data.client_message_id))
            if existing:
                if existing.conversation_id != cid or existing.body != data.body or existing.reply_to_id != data.reply_to_id:
                    raise AppError(409, "idempotency_conflict", "That send ID was already used for a different message.")
                return messages_json(session, [existing], uid)[0], [], False
            if data.reply_to_id:
                reply = require_visible_message(session, data.reply_to_id, uid)
                if reply.conversation_id != cid:
                    raise AppError(400, "invalid_reply", "A reply must reference this conversation.")
            message = Message(conversation_id=cid, sender_id=uid, body=data.body,
                              client_message_id=data.client_message_id, created_at=now(), reply_to_id=data.reply_to_id)
            session.add(message)
            session.flush()
            audience = active_users(session, cid)
            for target in audience:
                if target != uid:
                    session.add(Recipient(message_id=message.id, user_id=target))
            session.get(Conversation, cid).updated_at = message.created_at
            session.flush()
            result = messages_json(session, [message], uid)[0]
        return result, audience, True

    def pending(self, uid: int, limit: int = 100):
        with self.db.read() as session:
            items = list(session.scalars(select(Message).join(Recipient).join(Member,
                (Member.conversation_id == Message.conversation_id) & (Member.user_id == uid)).where(
                    Recipient.user_id == uid, Recipient.delivered_at.is_(None), Member.active.is_(True))
                .order_by(Message.id).limit(limit)))
            return messages_json(session, items, uid)

    def receipts(self, uid: int, ids: list[int], state: str):
        with self.db.write() as session:
            rows = list(session.execute(select(Recipient, Message.conversation_id).join(Message).join(Member,
                (Member.conversation_id == Message.conversation_id) & (Member.user_id == uid)).where(
                    Recipient.user_id == uid, Recipient.message_id.in_(set(ids)), Member.active.is_(True))))
            changed: set[int] = set()
            tick = now()
            for row, cid in rows:
                if row.delivered_at is None:
                    row.delivered_at = tick
                    changed.add(cid)
                if state == "read" and row.read_at is None:
                    row.read_at = tick
                    changed.add(cid)
            return {cid: active_users(session, cid) for cid in changed}

    def react(self, uid: int, mid: int, emoji: str):
        with self.db.write() as session:
            message = require_visible_message(session, mid, uid)
            current = session.get(Reaction, (mid, uid))
            if current and current.emoji == emoji:
                session.delete(current)
            elif current:
                current.emoji = emoji
            else:
                session.add(Reaction(message_id=mid, user_id=uid, emoji=emoji))
            audience = active_users(session, message.conversation_id)
            return message.conversation_id, audience

    def typing_audience(self, uid: int, cid: int):
        with self.db.read() as session:
            require_member(session, cid, uid)
            return active_users(session, cid)
