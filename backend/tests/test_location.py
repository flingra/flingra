import httpx

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
