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


def test_location_search_returns_google_places_results(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    request_options = {}
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

    def fake_post(url, **kwargs):
        request_options["url"] = url
        request_options.update(kwargs)
        return response

    monkeypatch.setattr(location.httpx, "post", fake_post)

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
    assert request_options["url"] == location.GOOGLE_PLACES_SEARCH_URL
    assert request_options["headers"]["X-Goog-Api-Key"] == "test-key"
    assert request_options["headers"]["X-Goog-FieldMask"] == location.GOOGLE_PLACES_FIELD_MASK
    assert request_options["json"]["textQuery"] == "Lekki Conservation Center, Nigeria"
    assert request_options["json"]["regionCode"] == "NG"


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
    monkeypatch.setattr(location.httpx, "post", lambda *_args, **_kwargs: response)

    result = client.get("/location/search", params={"q": "Lekki"})

    assert result.status_code == 200
    assert result.json() == {"results": []}


def test_location_search_reports_provider_outage(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        429,
        request=httpx.Request("POST", location.GOOGLE_PLACES_SEARCH_URL),
    )
    monkeypatch.setattr(location.httpx, "post", lambda *_args, **_kwargs: response)

    result = client.get("/location/search", params={"q": "Lekki"})

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
    request_options = {}
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

    def fake_get(url, **kwargs):
        request_options["url"] = url
        request_options.update(kwargs)
        return response

    monkeypatch.setattr(location.httpx, "get", fake_get)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert request_options["url"] == location.GOOGLE_GEOCODING_URL
    assert request_options["params"]["key"] == "test-key"
    assert request_options["params"]["region"] == "ng"


def test_reverse_geocode_returns_no_area_for_zero_results(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        200,
        json={"status": "ZERO_RESULTS", "results": []},
        request=httpx.Request("GET", location.GOOGLE_GEOCODING_URL),
    )
    monkeypatch.setattr(location.httpx, "get", lambda *_args, **_kwargs: response)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": None}
