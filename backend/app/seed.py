"""Fictional accounts and conversations. Only seed an empty database."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from .models import Contact, Conversation, Member, Message, Reaction, Recipient, User


def seed_demo(db):
    with db.write() as session:
        if session.scalar(select(func.count()).select_from(User)):
            return
        base = datetime.now(timezone.utc)
        stamp = lambda minutes: (base - timedelta(minutes=minutes)).isoformat(timespec="milliseconds")
        specs = [
            ("alex", "Alex Morgan", "blue"), ("maya", "Maya Chen", "pink"),
            ("sam", "Sam Rivera", "teal"), ("priya", "Priya Shah", "purple"),
            ("leo", "Leo Park", "orange"), ("nina", "Nina Patel", "pink"),
        ]
        users = []
        for username, name, color in specs:
            user = User(username=username, display_name=name, color=color, created_at=stamp(5000), last_seen=stamp(15))
            session.add(user)
            session.flush()
            users.append(user)
        for owner in users:
            for other in users:
                if owner.id != other.id:
                    session.add(Contact(owner_id=owner.id, contact_id=other.id))

        def conversation(ids, name=None):
            kind = "group" if name else "direct"
            item = Conversation(kind=kind, name=name, creator_id=ids[0],
                direct_key=None if name else ":".join(map(str, sorted(ids))), created_at=stamp(3000), updated_at=stamp(3000))
            session.add(item)
            session.flush()
            for uid in ids:
                session.add(Member(conversation_id=item.id, user_id=uid, role="admin" if name and uid == ids[0] else "member",
                                   active=True, joined_at=stamp(3000)))
            session.flush()
            return item

        def message(conv, sender, body, minutes, unread=False, reply=None):
            item = Message(conversation_id=conv.id, sender_id=sender, body=body,
                client_message_id=f"seed-{conv.id}-{minutes}-{sender}", created_at=stamp(minutes), reply_to_id=reply)
            session.add(item)
            session.flush()
            for uid in session.scalars(select(Member.user_id).where(Member.conversation_id == conv.id)):
                if uid != sender:
                    session.add(Recipient(message_id=item.id, user_id=uid, delivered_at=stamp(minutes),
                                          read_at=None if unread and uid == users[0].id else stamp(minutes)))
            conv.updated_at = item.created_at
            return item

        a, m, s, p, l, n = [u.id for u in users]
        direct = conversation([a, m])
        message(direct, m, "Hey! Did you get a chance to look at the place I sent over?", 1520)
        message(direct, a, "I did, it looks lovely. The windows sold me honestly.", 1517)
        message(direct, m, "Right? So much natural light ☀️", 1515)
        message(direct, a, "We should go see it this weekend.", 1510)
        message(direct, m, "Saturday works for me. How about coffee first?", 26)
        first = message(direct, a, "Perfect. Same little place on the corner?", 24)
        message(direct, m, "Yes! I've been thinking about their cinnamon rolls all week.", 23, reply=first.id)
        message(direct, a, "That's settled then. 10:30?", 20)
        message(direct, m, "10:30 it is. See you there 😊", 3, unread=True)
        session.add(Reaction(message_id=first.id, user_id=m, emoji="❤️"))
        group = conversation([a, s, p, l], "Weekend people")
        message(group, s, "Officially putting a hike on the calendar. Who's in?", 150)
        message(group, p, "Me, as long as we stop for breakfast on the way.", 145)
        message(group, a, "Breakfast is non-negotiable.", 140)
        message(group, l, "Found an easy trail by the lake. I'll send the details tonight.", 17, unread=True)
        message(group, s, "I'm bringing the questionable playlist 🎵", 15, unread=True)
        direct2 = conversation([a, p])
        message(direct2, p, "The book you lent me was so good.", 185)
        message(direct2, a, "That ending! I need to talk about it.", 180)
        message(direct2, p, "Call me when you're free. I have theories.", 65)
        direct3 = conversation([a, s])
        message(direct3, s, "Made it home. Thanks for dinner!", 950)
        message(direct3, a, "Anytime. Your turn to cook next week.", 940)
        message(direct3, s, "Deal 🤝", 900)
        group2 = conversation([a, m, n], "The reading room")
        message(group2, n, "New month, new book. Something a little lighter this time?", 1850)
        message(group2, m, "Please. I still haven't recovered from the last one.", 1840)
        message(group2, a, "I'll put together a shortlist this weekend.", 1820)
        direct4 = conversation([a, l])
        message(direct4, l, "Sent the photos from Sunday. There are a few good ones!", 2300)
        message(direct4, a, "The last one is definitely going on the wall.", 2290)
