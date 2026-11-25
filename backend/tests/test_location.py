import httpx

from app.config import Settings
from app.routes import auth, location


def authenticated_location_client(api_client):
    client, _ = api_client
    client.app.dependency_overrides[auth.get_authenticated_account] = lambda: auth.AuthenticatedAccount(
        {"id": "test-account", "email_verified": True, "onboarding_complete": True}
    )
    return client


def test_location_search_returns_nominatim_results_and_identifies_app(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    request_options = {}
    response = httpx.Response(
        200,
        json=[
            {
                "display_name": "Lekki Conservation Center, Lagos, Nigeria",
                "lat": "6.436208",
                "lon": "3.535577",
                "address": {"park": "Lekki Conservation Center", "state": "Lagos"},
            }
        ],
        request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
    )

    def fake_get(_url, **kwargs):
        request_options.update(kwargs)
        return response

    monkeypatch.setattr(location.httpx, "get", fake_get)

    result = client.get("/location/search", params={"q": "Lekki Conservation Center"})

    assert result.status_code == 200
    assert result.json() == {
        "results": [
            {
                "name": "Lekki Conservation Center, Lagos, Nigeria",
                "area": "Lekki Conservation Center",
                "latitude": 6.436208,
                "longitude": 3.535577,
            }
        ]
    }
    assert request_options["headers"]["User-Agent"] == location.NOMINATIM_USER_AGENT
    assert request_options["params"]["countrycodes"] == "ng"


def test_location_search_reports_provider_outage(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        429,
        request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
    )
    monkeypatch.setattr(location.httpx, "get", lambda *_args, **_kwargs: response)

    result = client.get("/location/search", params={"q": "Lekki"})

    assert result.status_code == 503
    assert result.json()["error"]["message"] == "Location search is temporarily unavailable."


def test_location_search_falls_back_to_photon(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)

    def fake_get(url, **_kwargs):
        if "nominatim" in url:
            return httpx.Response(
                503,
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "properties": {
                            "name": "Lekki",
                            "city": "Lagos",
                            "state": "Lagos",
                            "country": "Nigeria",
                        },
                        "geometry": {"coordinates": [3.535, 6.436]},
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(location.httpx, "get", fake_get)

    result = client.get("/location/search", params={"q": "Lekki"})

    assert result.status_code == 200
    assert result.json()["results"] == [
        {
            "name": "Lekki, Lagos, Nigeria",
            "area": "Lekki",
            "latitude": 6.436,
            "longitude": 3.535,
        }
    ]


def test_reverse_geocode_uses_configured_opencage_key(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    client.app.state.settings = Settings(opencage_api_key="test-key")
    request_options = {}
    response = httpx.Response(
        200,
        json={
            "results": [
                {
                    "components": {
                        "suburb": "Lekki",
                        "city": "Lagos",
                        "state": "Lagos",
                        "country_code": "ng",
                    }
                }
            ]
        },
        request=httpx.Request("GET", "https://api.opencagedata.com/geocode/v1/json"),
    )

    def fake_get(url, **kwargs):
        request_options["url"] = url
        request_options.update(kwargs)
        return response

    monkeypatch.setattr(location.httpx, "get", fake_get)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert request_options["url"] == "https://api.opencagedata.com/geocode/v1/json"
    assert request_options["params"]["key"] == "test-key"


def test_reverse_geocode_falls_back_to_nominatim(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    client.app.state.settings = Settings(opencage_api_key="test-key")
    requests = []

    def fake_get(url, **_kwargs):
        requests.append(url)
        if "opencage" in url:
            return httpx.Response(503, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            json={
                "address": {
                    "suburb": "Lekki",
                    "city": "Lagos",
                    "state": "Lagos",
                    "country_code": "ng",
                }
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(location.httpx, "get", fake_get)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert requests == [
        "https://api.opencagedata.com/geocode/v1/json",
        "https://nominatim.openstreetmap.org/reverse",
    ]
