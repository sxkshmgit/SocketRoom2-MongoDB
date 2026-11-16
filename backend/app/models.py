from dataclasses import dataclass
from datetime import datetime

GENERAL_ROOM_ID = 1


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    created_at: datetime


@dataclass
class Message:
    id: int
    sender_id: int
    sender_username: str
    content: str
    created_at: datetime
    room_id: int = GENERAL_ROOM_ID


@dataclass
class Conversation:
    id: int
    user_low_id: int
    user_high_id: int
    created_at: datetime
    user_low: User
    user_high: User

    def other_user(self, user_id: int) -> User:
        return self.user_high if user_id == self.user_low_id else self.user_low


@dataclass
class PrivateMessage:
    id: int
    conversation_id: int
    sender_id: int
    sender_username: str
    content: str
    created_at: datetime
