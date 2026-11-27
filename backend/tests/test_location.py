import json

import httpx
import pytest

from app.config import Settings
from app.routes import auth, location


def authenticated_location_client(api_client):
    client, _ = api_client
    client.app.state.settings = Settings(google_maps_server_api_key="test-key")
    client.app.dependency_overrides[auth.get_authenticated_account] = lambda: auth.AuthenticatedAccount(
        {"id": "test-account", "email_verified": True, "onboarding_complete": True}
    )
    return client


def mock_google_response(monkeypatch, response: httpx.Response) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    original_client = location.httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: requests.append(request) or response
    )
    monkeypatch.setattr(
        location.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    return requests


def test_location_search_returns_google_places_results(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        200,
        json={"places": [
            {
                "displayName": {"text": "Lekki Conservation Centre"},
                "formattedAddress": "Lekki Conservation Centre, Lagos, Nigeria",
                "location": {"latitude": 6.436208, "longitude": 3.535577},
                "addressComponents": [
                    {"longText": "Lekki", "types": ["neighborhood"]},
                    {"longText": "Nigeria", "shortText": "NG", "types": ["country"]},
                ],
            }
        ]},
        request=httpx.Request("POST", location.GOOGLE_PLACES_SEARCH_URL),
    )
    requests = mock_google_response(monkeypatch, response)

    result = client.get("/location/search", params={"q": "Lekki Conservation Center"})

    assert result.status_code == 200
    assert result.json() == {
        "results": [
            {
                "name": "Lekki Conservation Centre",
                "area": "Lekki",
                "latitude": 6.436208,
                "longitude": 3.535577,
            }
        ]
    }
    assert len(requests) == 1
    assert str(requests[0].url) == location.GOOGLE_PLACES_SEARCH_URL
    assert requests[0].headers["X-Goog-Api-Key"] == "test-key"
    assert requests[0].headers["X-Goog-FieldMask"] == location.GOOGLE_PLACES_FIELD_MASK
    request_json = json.loads(requests[0].content)
    assert request_json["textQuery"] == "Lekki Conservation Center, Nigeria"
    assert request_json["regionCode"] == "NG"


def test_location_search_filters_non_nigerian_results(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        200,
        json={
            "places": [
                {
                    "displayName": {"text": "Somewhere outside Nigeria"},
                    "location": {"latitude": 10, "longitude": 20},
                    "addressComponents": [
                        {"longText": "Ghana", "types": ["country"]},
                    ],
                }
            ]
        },
        request=httpx.Request("POST", location.GOOGLE_PLACES_SEARCH_URL),
    )
    mock_google_response(monkeypatch, response)

    result = client.get("/location/search", params={"q": "Somewhere outside Nigeria"})

    assert result.status_code == 200
    assert result.json() == {"results": []}


def test_location_search_reports_provider_outage(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        429,
        request=httpx.Request("POST", location.GOOGLE_PLACES_SEARCH_URL),
    )
    mock_google_response(monkeypatch, response)

    result = client.get("/location/search", params={"q": "Provider outage check"})

    assert result.status_code == 503
    assert result.json()["error"]["message"] == "Google Maps location search is temporarily unavailable."


def test_location_search_requires_server_key(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    client.app.state.settings = Settings(google_maps_server_api_key=None)
    monkeypatch.setattr(
        location.httpx,
        "get",
        lambda *_args, **_kwargs: pytest.fail("Google Geocoding must not be called without a key"),
    )
    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})
    assert result.status_code == 503
    assert result.json()["error"]["message"] == "Google Maps location services are not configured."


def test_reverse_geocode_uses_google_and_returns_approximate_area(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    requests: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "status": "OK",
            "results": [
                {
                    "address_components": [
                        {"long_name": "Lekki", "types": ["neighborhood"]},
                        {"long_name": "Lagos", "types": ["locality"]},
                        {"long_name": "Nigeria", "short_name": "NG", "types": ["country"]},
                    ]
                }
            ],
        },
        request=httpx.Request("GET", location.GOOGLE_GEOCODING_URL),
    )

    requests = mock_google_response(monkeypatch, response)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert len(requests) == 1
    assert str(requests[0].url).startswith(location.GOOGLE_GEOCODING_URL)
    assert requests[0].url.params["key"] == "test-key"
    assert requests[0].url.params["region"] == "ng"


def test_reverse_geocode_returns_no_area_for_zero_results(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        200,
        json={"status": "ZERO_RESULTS", "results": []},
        request=httpx.Request("GET", location.GOOGLE_GEOCODING_URL),
    )
    mock_google_response(monkeypatch, response)

    result = client.get("/location/reverse", params={"latitude": 6.451, "longitude": 3.471})

    assert result.status_code == 200
    assert result.json() == {"area": None}
