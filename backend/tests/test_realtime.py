import pytest
from starlette.websockets import WebSocketDisconnect


def test_realtime_websocket_rejects_empty_origin_allowlist(api_client) -> None:
    client, _ = api_client
    client.app.state.settings.allowed_origins = []

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect(
            "/realtime/ws",
            headers={"Origin": "https://attacker.example.test"},
        ):
            pass

    assert disconnect.value.code == 4403


def test_realtime_websocket_rejects_non_allowlisted_origin(api_client) -> None:
    client, _ = api_client
    client.app.state.settings.allowed_origins = ["https://app.example.test"]

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect(
            "/realtime/ws",
            headers={"Origin": "https://attacker.example.test"},
        ):
            pass

    assert disconnect.value.code == 4403
