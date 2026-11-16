import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
import jwt
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import ValidationError
from pymongo.database import Database
from pymongo.errors import PyMongoError

from backend.app import crud, models, schemas, security
from backend.app.database import get_db, init_db
from backend.app.connection_manager import manager
from backend.app.dependencies import get_current_user, get_user_from_token

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/users", response_model=list[schemas.UserResponse])
def list_users(
    db: Database = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return crud.get_users(db)

@app.post(
    "/users",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(user_in: schemas.UserCreate, db: Database = Depends(get_db)):
    if crud.get_user_by_username(db, user_in.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    password_hash = security.hash_password(user_in.password)

    user = crud.create_user(db, user_in.username, password_hash)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    return user


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(login_in: schemas.LoginRequest, db: Database = Depends(get_db)):
    user = crud.get_user_by_username(db, login_in.username)

    if user is None or not security.verify_password(
        login_in.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(data={"sub": str(user.id)})
    return schemas.TokenResponse(access_token=access_token, token_type="bearer")

@app.get("/auth/me", response_model=schemas.UserResponse)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user

@app.get("/messages", response_model=list[schemas.MessageResponse])
def list_messages(
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return crud.get_recent_messages(db, limit)


def conversation_response(
    conversation: models.Conversation,
    current_user_id: int,
    last_message_at=None,
) -> schemas.ConversationResponse:
    other = conversation.other_user(current_user_id)
    return schemas.ConversationResponse(
        id=conversation.id,
        other_user_id=other.id,
        other_username=other.username,
        last_message_at=last_message_at,
    )


@app.post("/conversations", response_model=schemas.ConversationResponse)
def start_conversation(
    conversation_in: schemas.ConversationCreate,
    db: Database = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if conversation_in.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start a conversation with yourself",
        )

    if crud.get_user_by_id(db, conversation_in.user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    conversation = crud.get_or_create_conversation(
        db, current_user.id, conversation_in.user_id
    )

    latest = crud.get_recent_private_messages(db, conversation.id, limit=1)
    last_message_at = latest[0].created_at if latest else None
    return conversation_response(conversation, current_user.id, last_message_at)


@app.get("/conversations", response_model=list[schemas.ConversationResponse])
def list_conversations(
    db: Database = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        conversation_response(conversation, current_user.id, last_message_at)
        for conversation, last_message_at in crud.list_conversations_for_user(
            db, current_user.id
        )
    ]


@app.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[schemas.PrivateMessageResponse],
)
def list_private_messages(
    conversation_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conversation = crud.get_conversation_for_user(db, conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return crud.get_recent_private_messages(db, conversation.id, limit)

AUTH_TIMEOUT_SECONDS = 10


def authenticate_token(token: str) -> tuple[int, str, float] | None:
    try:
        expires_at = float(security.decode_access_token(token)["exp"])
    except jwt.InvalidTokenError:
        return None

    user = get_user_from_token(get_db(), token)
    if user is None:
        return None
    return user.id, user.username, expires_at


def save_chat_message(user_id: int, content: str) -> dict:
    message = crud.create_message(get_db(), user_id, content)
    return schemas.MessageResponse.model_validate(message).model_dump(mode="json")


def save_private_message(
    sender_id: int, conversation_id: int, content: str
) -> tuple[dict, set[int]] | None:
    db = get_db()
    conversation = crud.get_conversation_for_user(db, conversation_id, sender_id)
    if conversation is None:
        return None
    message = crud.create_private_message(db, conversation.id, sender_id, content)
    payload = schemas.PrivateMessageResponse.model_validate(message).model_dump(
        mode="json"
    )
    return payload, {conversation.user_low_id, conversation.user_high_id}


async def send_error(websocket: WebSocket, text: str) -> None:
    await websocket.send_json({"type": "error", "content": text})


async def handle_frame(websocket: WebSocket, user_id: int, frame) -> None:
    frame_type = frame.get("type") if isinstance(frame, dict) else None
    if frame_type not in ("message", "private_message"):
        await send_error(websocket, "Unsupported message type")
        return

    try:
        content = schemas.MessageCreate(content=frame.get("content")).content
    except ValidationError:
        await send_error(websocket, "Message content is invalid")
        return

    try:
        if frame_type == "message":
            payload = save_chat_message(user_id, content)
            await manager.broadcast({"type": "message", "data": payload})
            return

        conversation_id = frame.get("conversation_id")
        result = None
        if type(conversation_id) is int:
            result = save_private_message(user_id, conversation_id, content)
        if result is None:
            await send_error(websocket, "Conversation not found")
            return
        payload, participant_ids = result
        await manager.send_to_users(
            participant_ids, {"type": "private_message", "data": payload}
        )
    except PyMongoError:
        await send_error(websocket, "Message could not be saved")


@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        try:
            auth_frame = await asyncio.wait_for(
                websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, ValueError, KeyError, TypeError):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        token = None
        if isinstance(auth_frame, dict) and auth_frame.get("type") == "auth":
            auth_data = auth_frame.get("data")
            if isinstance(auth_data, dict):
                token = auth_data.get("token")

        try:
            identity = authenticate_token(token) if isinstance(token, str) else None
        except PyMongoError:
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return

        if identity is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id, username, expires_at = identity
        await websocket.send_json(
            {"type": "auth_ok", "data": {"user_id": user_id, "username": username}}
        )
        manager.connect(websocket, user_id)

        while True:
            remaining = expires_at - time.time()
            if remaining <= 0:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            try:
                frame = await asyncio.wait_for(
                    websocket.receive_json(), timeout=remaining
                )
            except asyncio.TimeoutError:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            except (ValueError, KeyError, TypeError):
                await send_error(websocket, "Invalid message format")
                continue

            await handle_frame(websocket, user_id, frame)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")