# SocketRoom2-MongoDB

A real-time chat application built with **FastAPI, WebSockets, MongoDB, and vanilla JavaScript**.

SocketRoom2 is a learning and portfolio project focused on backend fundamentals, authentication, database persistence, and real-time communication between connected clients.

This is the **MongoDB** version of the project. The same app using Microsoft SQL Server lives in [SocketRoom2](https://github.com/sxkshmgit/SocketRoom2).

## Features

- User registration and login.
- Password hashing with Argon2.
- JWT-based authentication for HTTP routes and WebSocket connections.
- A shared chatroom named **General**.
- **One-to-one private messaging**:
  - Start a private conversation with any registered user.
  - Exactly one conversation per pair of users, enforced by a unique index.
  - Real-time delivery to both participants, including every open tab.
  - A conversation list ordered by most recent activity, with unread markers.
  - Conversations and history persist across logout and login.
- Real-time message broadcasting over a single WebSocket connection.
- Persistent storage of users, conversations, and messages in MongoDB.
- Retrieval of recent message history (up to 100 messages per request).
- Automatic WebSocket reconnection after a dropped connection.
- A Retry option when loading chat history fails.
- Username normalization and validation.
- Different WebSocket close handling for invalid authentication and temporary database errors.
- Responsive layout: the chat sidebar collapses behind a menu button on narrow screens.

## Tech stack

| Area | Technology |
|---|---|
| Backend | Python, FastAPI |
| Real-time communication | WebSockets |
| Database | MongoDB |
| Database driver | PyMongo |
| Data validation | Pydantic v2 |
| Authentication | JWT, PyJWT |
| Password hashing | Argon2 through pwdlib |
| Frontend | HTML, CSS, vanilla JavaScript |
| Tests | Pytest (against mongomock, an in-memory fake MongoDB) |

## Project structure

~~~text
SocketRoom2-MongoDB/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Routes, WebSocket endpoint, startup
│   │   ├── connection_manager.py   # Tracks open sockets per user
│   │   ├── crud.py                 # Database queries
│   │   ├── database.py             # MongoDB connection, indexes, ID counter
│   │   ├── dependencies.py         # Current-user dependency
│   │   ├── models.py               # Dataclasses for users, conversations, messages
│   │   ├── schemas.py              # Pydantic request/response models
│   │   └── security.py             # Password hashing and JWTs
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/
│   ├── conftest.py
│   ├── test_authentication.py
│   ├── test_protected_routes.py
│   ├── test_database_setup.py
│   ├── test_websocket_general.py
│   ├── test_private_crud.py
│   ├── test_private_routes.py
│   └── test_websocket_private.py
└── .gitignore
~~~

## Getting started

### Prerequisites

- **MongoDB Community Server** running locally on the default port (27017).
- Optionally, **MongoDB Compass** to browse the data.
- Python 3.10 or newer.
- Git.
- A modern web browser.

### 1. Clone the repository

~~~bash
git clone https://github.com/sxkshmgit/SocketRoom2-MongoDB.git
cd SocketRoom2-MongoDB
~~~

### 2. Start MongoDB

Install MongoDB Community Server and make sure it is running (on Windows it installs as the **MongoDB** service). Nothing needs to be created by hand: MongoDB creates the **socketroom** database and its collections the first time the app saves something.

By default the app connects to **mongodb://localhost:27017** and uses the database **socketroom**. To use something else, set these environment variables before starting the app:

| Variable | Default |
|---|---|
| MONGO_URL | mongodb://localhost:27017 |
| MONGO_DB | socketroom |

To start again with no data, drop the **socketroom** database in MongoDB Compass (or run `db.dropDatabase()` in mongosh). The app recreates its indexes on the next start.

### 3. Create and activate a virtual environment

Create it from the project root:

~~~bash
python -m venv .venv
~~~

Activate it using the command for your terminal.

**Windows PowerShell**

~~~powershell
.venv\Scripts\Activate.ps1
~~~

**Git Bash**

~~~bash
source .venv/Scripts/activate
~~~

### 4. Install dependencies

Install the application and development dependencies:

~~~bash
python -m pip install -r backend/requirements-dev.txt
~~~

### 5. Set the JWT secret

The application reads the signing secret from the **JWT_SECRET_KEY** environment variable and will not start without it.

The following commands generate a random secret for a local development session.

**Windows PowerShell**

~~~powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

**Git Bash**

~~~bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
~~~

Keep the same terminal session open while running the application. If you generate a different secret later, JWTs signed with the previous secret will no longer validate, and users must log in again.

For deployment, configure a persistent secret through the hosting environment. Do not commit the secret to the repository.

### 6. Run the application

From the project root, with the virtual environment activated and the secret set:

~~~bash
python -m uvicorn backend.app.main:app --reload
~~~

Open the application:

~~~text
http://127.0.0.1:8000
~~~

On startup, the application checks that MongoDB is reachable and creates its indexes. If MongoDB is not running, startup stops after about 3 seconds with a connection error.

To try private messaging, log in as two different users in two browser tabs or windows. Each tab keeps its own session.

The interactive API documentation is available at:

~~~text
http://127.0.0.1:8000/docs
~~~

## How it works

### Authentication

1. A user registers with a username and password.
2. The backend trims and lowercases new usernames and validates the allowed characters.
3. The password is hashed using Argon2 before it is stored.
4. During login, the backend verifies the password and issues a JWT that expires after 30 minutes.
5. The frontend stores the token in session storage.
6. Protected HTTP requests send the token in the Authorization header.
7. For WebSocket authentication, the client sends the token in the first JSON frame after connecting.

New usernames may contain letters, numbers, underscores, hyphens, and periods, with a maximum length of 50 characters. New passwords must be 8–128 characters long. Login permits existing shorter passwords for compatibility and accepts username capitalization differences for normalized accounts.

### Real-time message flow

General and private messages share one WebSocket connection per browser tab.

1. The browser opens a WebSocket connection to the backend.
2. The client sends its JWT in an authentication frame.
3. The backend validates the token, confirms the connection, and records which user owns the socket.
4. The client sends a **message** frame (General) or a **private_message** frame (private chat).
5. The backend validates the content and saves it. For private messages, it first checks that the sender is a participant in the conversation.
6. General messages are broadcast to every connected socket. Private messages are sent only to the sockets of the two participants.
7. Connected clients render the message if it belongs to the chat currently open, or mark that chat as unread.

The frontend reconnects 2 seconds after an unexpected WebSocket closure and then reloads the open chat's history and the conversation list. Invalid authentication closes the connection with code **1008**; a temporary database error during WebSocket authentication uses **1013**, allowing the client to retry without clearing its token.

### Private conversations

- A conversation stores its two users as **user_low_id** and **user_high_id** (the smaller ID first), and a unique index on that pair guarantees one conversation per pair, regardless of who starts it.
- Starting a conversation is a get-or-create operation, so it is safe to call repeatedly or from both users at once.
- Only participants can read a conversation's history or send messages to it. Non-participants receive the same "not found" response as for a conversation that does not exist, so conversation IDs are not revealed.
- The conversation list only includes conversations with at least one message.

### Chat history

Authenticated HTTP endpoints return recent messages in chronological order. They accept a **limit** query parameter between 1 and 100.

Examples:

~~~http
GET /messages?limit=50
GET /conversations/7/messages?limit=50
~~~

If loading history fails, the frontend shows an error with a Retry button.

## API endpoints

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | / | Serves the frontend | No |
| GET | /health | Health check | No |
| POST | /users | Registers a user | No |
| POST | /auth/login | Authenticates a user and returns a JWT | No |
| GET | /auth/me | Returns the authenticated user | Yes |
| GET | /users | Lists registered users | Yes |
| GET | /messages | Returns recent General chat history | Yes |
| POST | /conversations | Gets or creates a conversation with another user | Yes |
| GET | /conversations | Lists your conversations, newest activity first | Yes |
| GET | /conversations/{id}/messages | Returns recent history for a conversation you belong to | Yes |

Static frontend assets are served under **/static**.

### Starting a conversation

~~~http
POST /conversations
Content-Type: application/json

{ "user_id": 2 }
~~~

Response:

~~~json
{
  "id": 7,
  "other_user_id": 2,
  "other_username": "bob",
  "last_message_at": null
}
~~~

Errors: **400** when starting a conversation with yourself, **404** for an unknown user.

**GET /conversations** returns a list of the same objects. **GET /conversations/{id}/messages** returns **404** if the conversation does not exist or you are not a participant.

## WebSocket protocol

The WebSocket endpoint is:

~~~text
ws://127.0.0.1:8000/ws
~~~

When the application is served over HTTPS, the frontend uses secure WebSockets (**wss://**).

### 1. Authentication frame

The first client frame must contain the JWT and must be sent within 10 seconds:

~~~json
{
  "type": "auth",
  "data": {
    "token": "YOUR_JWT_TOKEN"
  }
}
~~~

### 2. Authentication success

The server responds with:

~~~json
{
  "type": "auth_ok",
  "data": {
    "user_id": 1,
    "username": "alice"
  }
}
~~~

### 3. Send a General message

~~~json
{
  "type": "message",
  "content": "Hello everyone!"
}
~~~

Every connected client receives:

~~~json
{
  "type": "message",
  "data": {
    "id": 1,
    "room_id": 1,
    "sender_id": 1,
    "sender_username": "alice",
    "content": "Hello everyone!",
    "created_at": "2026-11-06T10:00:00"
  }
}
~~~

### 4. Send a private message

Create or look up the conversation first with **POST /conversations**, then send:

~~~json
{
  "type": "private_message",
  "conversation_id": 7,
  "content": "Hi Bob!"
}
~~~

Both participants receive the following on every open connection, including the sender's:

~~~json
{
  "type": "private_message",
  "data": {
    "id": 1,
    "conversation_id": 7,
    "sender_id": 1,
    "sender_username": "alice",
    "content": "Hi Bob!",
    "created_at": "2026-11-06T10:01:00"
  }
}
~~~

General and private messages are numbered independently, so an **id** is only unique within its own chat.

### 5. Errors

Invalid frames do not close the connection. The server replies with an error frame:

~~~json
{
  "type": "error",
  "content": "Conversation not found"
}
~~~

Possible messages: **Invalid message format**, **Unsupported message type**, **Message content is invalid** (empty after trimming, or longer than 2000 characters), **Conversation not found**, and **Message could not be saved**.

## How data is stored

MongoDB stores documents in collections:

| Collection | Example document |
|---|---|
| users | `{ id: 1, username: "alice", password_hash: "...", created_at }` |
| messages (General) | `{ id: 1, sender_id: 1, sender_username: "alice", content: "hi", created_at }` |
| conversations | `{ id: 1, user_low_id: 1, user_high_id: 2, created_at }` |
| private_messages | `{ id: 1, conversation_id: 1, sender_id: 1, sender_username: "alice", content: "hi", created_at }` |
| counters | `{ _id: "users", value: 1 }` |

- **Numeric IDs:** MongoDB's own `_id` values are long strings, so the app hands out its own numbers (1, 2, 3, ...) from the **counters** collection. That keeps the API and frontend simple.
- **Unique indexes** replace database constraints: one account per username, one conversation per pair of users, and one document per ID.
- **No joins:** each message stores its sender's username, so loading history is a single query. Usernames cannot change, so the copy never goes stale.
- **No foreign keys:** MongoDB does not check that IDs point to real documents, so the code checks this itself (for example, only conversation members can post, and messages from unknown users are rejected).

## Running tests

The test suite uses Pytest. Tests run against **mongomock**, an in-memory fake MongoDB, so MongoDB does not need to be running and your real data is never touched. From the project root, with development dependencies installed, run:

~~~bash
python -m pytest -v
~~~

The tests cover:

- User registration and login, and duplicate usernames.
- Protected HTTP routes.
- Database setup: unique indexes and the ID counter.
- General chat over WebSockets: authentication, broadcasting, persistence, invalid frames, and disconnects.
- Private chat data layer: one conversation per pair, participant checks, history ordering and limits.
- Private chat HTTP endpoints, including authorization and error codes.
- Private chat over WebSockets: delivery only to participants, multiple tabs, offline recipients, and rejection of non-participants.

## Project scope and limitations

SocketRoom2 is intentionally a small application. Its current design has these limitations:

- **Single process:** active WebSocket connections are held in memory by one connection manager. Run the application with a single Uvicorn worker; multiple workers would maintain separate connection lists and would not deliver messages across processes.
- **No schema migrations:** documents have no enforced schema. If a document's fields change, existing documents must be updated manually.
- **Recent history only:** the API returns up to 100 recent messages per request. Older-message pagination is not implemented.
- **No explicit send acknowledgement:** the WebSocket protocol does not provide a client message ID and server acknowledgement for each send. A connection failure at the wrong moment can therefore leave the sender unsure whether a message was saved.
- **Short sessions, no refresh:** tokens expire after 30 minutes, and the server then closes the WebSocket with code 1008, so users must log in again. There is no token refresh.
- **Unread markers are not stored:** they are set only by messages received live, and reset on page reload. Messages that arrive while disconnected appear in history but are not marked unread. Newly registered users appear in the "Start a chat" list after a reconnect or page reload.
- **No distributed broker:** there is no Redis or other pub/sub layer for coordinating multiple application processes.
- **Basic abuse protection:** rate limiting, connection caps, user blocking, and production-grade abuse controls are not implemented.

The project is intended for learning, demonstration, and portfolio use. It is not presented as a hardened public messaging service.

## Learning goals

This project provides hands-on practice with:

- Building REST endpoints with FastAPI.
- Validating request and response data with Pydantic.
- Hashing passwords and issuing JWTs.
- Modeling data as MongoDB documents, with unique indexes that enforce business rules.
- Persisting data in MongoDB with PyMongo.
- Authenticating and managing WebSocket connections.
- Broadcasting messages and delivering targeted messages to specific users.
- Enforcing authorization so users can only access their own conversations.
- Connecting a vanilla JavaScript frontend to a Python backend.
- Handling reconnects and failed history requests.
- Testing backend behavior with Pytest.

## License

No license has been added to this repository yet.
