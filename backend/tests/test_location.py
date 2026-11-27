import httpx

from app.config import Settings
from app.routes import auth, location


def authenticated_location_client(api_client):
    client, _ = api_client
    client.app.dependency_overrides[auth.get_authenticated_account] = lambda: auth.AuthenticatedAccount(
        {"id": "test-account", "email_verified": True, "onboarding_complete": True}
    )
    return client


def mock_provider_responses(monkeypatch, responses: list[httpx.Response]) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    original_client = location.httpx.AsyncClient

    def client_factory(**kwargs):
        transport = httpx.MockTransport(
            lambda request: requests.append(request) or responses.pop(0)
        )
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(location.httpx, "AsyncClient", client_factory)
    return requests


def test_location_search_returns_nominatim_results_without_maps_key(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
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
        request=httpx.Request("GET", location.NOMINATIM_SEARCH_URL),
    )
    requests = mock_provider_responses(monkeypatch, [response])

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
    assert len(requests) == 1
    assert requests[0].url.host == "nominatim.openstreetmap.org"
    assert requests[0].headers["User-Agent"] == location.NOMINATIM_USER_AGENT
    assert requests[0].url.params["countrycodes"] == "ng"


def test_location_search_falls_back_to_photon(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    responses = [
        httpx.Response(
            503,
            request=httpx.Request("GET", location.NOMINATIM_SEARCH_URL),
        ),
        httpx.Response(
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
            request=httpx.Request("GET", location.PHOTON_SEARCH_URL),
        ),
    ]
    requests = mock_provider_responses(monkeypatch, responses)

    result = client.get("/location/search", params={"q": "Lekki fallback test"})

    assert result.status_code == 200
    assert result.json()["results"] == [
        {
            "name": "Lekki, Lagos, Nigeria",
            "area": "Lekki",
            "latitude": 6.436,
            "longitude": 3.535,
        }
    ]
    assert [request.url.host for request in requests] == [
        "nominatim.openstreetmap.org",
        "photon.komoot.io",
    ]


def test_location_search_reports_error_when_both_providers_fail(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    mock_provider_responses(
        monkeypatch,
        [
            httpx.Response(429, request=httpx.Request("GET", location.NOMINATIM_SEARCH_URL)),
            httpx.Response(503, request=httpx.Request("GET", location.PHOTON_SEARCH_URL)),
        ],
    )

    result = client.get("/location/search", params={"q": "Unavailable location test"})

    assert result.status_code == 503
    assert result.json()["error"]["message"] == "Location search is temporarily unavailable."


def test_reverse_geocode_uses_configured_opencage_key(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    client.app.state.settings = Settings(opencage_api_key="test-key")
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
        request=httpx.Request("GET", location.OPENCAGE_REVERSE_URL),
    )
    requests = mock_provider_responses(monkeypatch, [response])

    result = client.get("/location/reverse", params={"latitude": 6.453, "longitude": 3.473})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert requests[0].url.host == "api.opencagedata.com"
    assert requests[0].url.params["key"] == "test-key"


def test_reverse_geocode_falls_back_to_nominatim(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    client.app.state.settings = Settings(opencage_api_key="test-key")
    responses = [
        httpx.Response(503, request=httpx.Request("GET", location.OPENCAGE_REVERSE_URL)),
        httpx.Response(
            200,
            json={
                "address": {
                    "suburb": "Lekki",
                    "city": "Lagos",
                    "state": "Lagos",
                    "country_code": "ng",
                }
            },
            request=httpx.Request("GET", location.NOMINATIM_REVERSE_URL),
        ),
    ]
    requests = mock_provider_responses(monkeypatch, responses)

    result = client.get("/location/reverse", params={"latitude": 6.45, "longitude": 3.47})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert [request.url.host for request in requests] == [
        "api.opencagedata.com",
        "nominatim.openstreetmap.org",
    ]


def test_reverse_geocode_uses_nominatim_without_opencage_key(api_client, monkeypatch) -> None:
    client = authenticated_location_client(api_client)
    response = httpx.Response(
        200,
        json={
            "address": {
                "neighbourhood": "Lekki",
                "city": "Lagos",
                "country_code": "ng",
            }
        },
        request=httpx.Request("GET", location.NOMINATIM_REVERSE_URL),
    )
    requests = mock_provider_responses(monkeypatch, [response])

    result = client.get("/location/reverse", params={"latitude": 6.452, "longitude": 3.472})

    assert result.status_code == 200
    assert result.json() == {"area": "Lekki, Lagos"}
    assert [request.url.host for request in requests] == ["nominatim.openstreetmap.org"]
