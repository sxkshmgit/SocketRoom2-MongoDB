import time
from contextlib import contextmanager

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.connection_manager import manager


def register_and_login(client, username):
    password = f"{username}-password"
    response = client.post("/users", json={"username": username, "password": password})
    assert response.status_code == 201
    login_response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    return response.json()["id"], login_response.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def connect_authenticated(client, token):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "data": {"token": token}})
        assert ws.receive_json()["type"] == "auth_ok"
        yield ws


def assert_closed_1008(ws):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        ws.receive_json()
    assert exc_info.value.code == 1008


def assert_error(ws, text):
    frame = ws.receive_json()
    assert frame["type"] == "error"
    assert frame["content"] == text


def wait_for_connections(expected, timeout=2.0):
    deadline = time.monotonic() + timeout
    while len(manager.active_connections) != expected and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(manager.active_connections) == expected
