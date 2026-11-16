from datetime import datetime, timezone

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from backend.app.database import next_id
from backend.app.models import Conversation, Message, PrivateMessage, User

NO_MONGO_ID = {"_id": False}


def _now() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def get_user_by_id(db: Database, user_id: int) -> User | None:
    document = db.users.find_one({"id": user_id}, NO_MONGO_ID)
    return User(**document) if document else None


def get_users(db: Database) -> list[User]:
    return [User(**document) for document in db.users.find({}, NO_MONGO_ID).sort("id", 1)]


def get_user_by_username(db: Database, username: str) -> User | None:
    document = db.users.find_one({"username": username.lower()}, NO_MONGO_ID)
    return User(**document) if document else None


def create_user(db: Database, username: str, password_hash: str) -> User | None:
    user = User(
        id=next_id(db, "users"),
        username=username.lower(),
        password_hash=password_hash,
        created_at=_now(),
    )
    try:
        db.users.insert_one(vars(user).copy())
    except DuplicateKeyError:
        return None
    return user


def _require_user(db: Database, user_id: int) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise ValueError(f"User {user_id} does not exist")
    return user


def create_message(db: Database, sender_id: int, content: str) -> Message:
    sender = _require_user(db, sender_id)
    message = Message(
        id=next_id(db, "messages"),
        sender_id=sender.id,
        sender_username=sender.username,
        content=content,
        created_at=_now(),
    )
    document = vars(message).copy()
    del document["room_id"]
    db.messages.insert_one(document)
    return message


def get_recent_messages(db: Database, limit: int = 50) -> list[Message]:
    newest_first = db.messages.find({}, NO_MONGO_ID).sort("id", -1).limit(limit)
    return [Message(**document) for document in reversed(list(newest_first))]


def _ordered_pair(user_a_id: int, user_b_id: int) -> tuple[int, int]:
    return (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)


def _to_conversation(db: Database, document: dict) -> Conversation:
    return Conversation(
        **document,
        user_low=get_user_by_id(db, document["user_low_id"]),
        user_high=get_user_by_id(db, document["user_high_id"]),
    )


def get_conversation_between_users(
    db: Database, user_a_id: int, user_b_id: int
) -> Conversation | None:
    if user_a_id == user_b_id:
        return None
    low_id, high_id = _ordered_pair(user_a_id, user_b_id)
    document = db.conversations.find_one(
        {"user_low_id": low_id, "user_high_id": high_id}, NO_MONGO_ID
    )
    return _to_conversation(db, document) if document else None


def get_or_create_conversation(
    db: Database, user_id: int, other_user_id: int
) -> Conversation:
    if user_id == other_user_id:
        raise ValueError("Cannot create a conversation with yourself")
    _require_user(db, user_id)
    _require_user(db, other_user_id)

    conversation = get_conversation_between_users(db, user_id, other_user_id)
    if conversation is not None:
        return conversation

    low_id, high_id = _ordered_pair(user_id, other_user_id)
    document = {
        "id": next_id(db, "conversations"),
        "user_low_id": low_id,
        "user_high_id": high_id,
        "created_at": _now(),
    }
    try:
        db.conversations.insert_one(document.copy())
    except DuplicateKeyError:
        return get_conversation_between_users(db, user_id, other_user_id)
    return _to_conversation(db, document)


def get_conversation_for_user(
    db: Database, conversation_id: int, user_id: int
) -> Conversation | None:
    document = db.conversations.find_one(
        {
            "id": conversation_id,
            "$or": [{"user_low_id": user_id}, {"user_high_id": user_id}],
        },
        NO_MONGO_ID,
    )
    return _to_conversation(db, document) if document else None


def create_private_message(
    db: Database, conversation_id: int, sender_id: int, content: str
) -> PrivateMessage:
    sender = _require_user(db, sender_id)
    message = PrivateMessage(
        id=next_id(db, "private_messages"),
        conversation_id=conversation_id,
        sender_id=sender.id,
        sender_username=sender.username,
        content=content,
        created_at=_now(),
    )
    db.private_messages.insert_one(vars(message).copy())
    return message


def get_recent_private_messages(
    db: Database, conversation_id: int, limit: int = 50
) -> list[PrivateMessage]:
    newest_first = (
        db.private_messages.find({"conversation_id": conversation_id}, NO_MONGO_ID)
        .sort("id", -1)
        .limit(limit)
    )
    return [PrivateMessage(**document) for document in reversed(list(newest_first))]


def list_conversations_for_user(
    db: Database, user_id: int
) -> list[tuple[Conversation, datetime]]:
    my_conversations = {
        document["id"]: document
        for document in db.conversations.find(
            {"$or": [{"user_low_id": user_id}, {"user_high_id": user_id}]}, NO_MONGO_ID
        )
    }
    last_activity = db.private_messages.aggregate([
        {"$match": {"conversation_id": {"$in": list(my_conversations)}}},
        {"$group": {
            "_id": "$conversation_id",
            "last_message_id": {"$max": "$id"},
            "last_message_at": {"$max": "$created_at"},
        }},
        {"$sort": {"last_message_id": -1}},
    ])
    return [
        (_to_conversation(db, my_conversations[row["_id"]]), row["last_message_at"])
        for row in last_activity
    ]
