import os

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

SQL_SERVER = r".\SQLEXPRESS"
DATABASE_NAME = "SocketRoomDB"
ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

DATABASE_URL = URL.create(
    drivername="mssql+pyodbc",
    host=SQL_SERVER,
    database=DATABASE_NAME,
    query={"driver": ODBC_DRIVER},
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "socketroom")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
db = client[MONGO_DB]


def get_db() -> Database:
    return db


def init_db() -> None:
    database = get_db()
    database.command("ping")

    for name in ("users", "messages", "conversations", "private_messages"):
        database[name].create_index("id", unique=True)

    database.users.create_index("username", unique=True)
    database.conversations.create_index(
        [("user_low_id", ASCENDING), ("user_high_id", ASCENDING)], unique=True
    )
    database.private_messages.create_index(
        [("conversation_id", ASCENDING), ("id", ASCENDING)]
    )


def next_id(database: Database, name: str) -> int:
    counter = database.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return counter["value"]
