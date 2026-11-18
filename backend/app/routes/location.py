from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.errors import ServiceUnavailable
from app.routes.auth import CurrentAccount, get_app_settings

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/search")
def search_locations(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    q: str = Query(min_length=2, max_length=120),
) -> dict[str, list[dict[str, str | float]]]:
    search_query = q if "nigeria" in q.casefold() else f"{q}, Nigeria"
    params: dict[str, str | int] = {
        "q": search_query,
        "format": "jsonv2",
        "limit": 15,
        "countrycodes": "ng",
        "addressdetails": 1,
        "dedupe": 1,
        "namedetails": 1,
    }

    if settings.opencage_api_key is not None:
        try:
            response = httpx.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={
                    "q": q,
                    "key": settings.opencage_api_key.get_secret_value(),
                    "language": "en",
                    "countrycode": "ng",
                    "limit": 15,
                    "no_annotations": "1",
                },
                timeout=httpx.Timeout(5.0, connect=2.0),
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            matches: list[dict[str, str | float]] = []
            seen: set[tuple[float, float]] = set()
            for item in results:
                geometry = item.get("geometry") or {}
                components = item.get("components") or {}
                name = item.get("formatted")
                if isinstance(name, str) and isinstance(geometry.get("lat"), (int, float)) and isinstance(geometry.get("lng"), (int, float)):
                    latitude = round(float(geometry["lat"]), 6)
                    longitude = round(float(geometry["lng"]), 6)
                    position = (latitude, longitude)
                    if position in seen:
                        continue
                    seen.add(position)
                    area = next(
                        (components[key] for key in (
                            "building", "road", "neighbourhood", "suburb", "quarter",
                            "city_district", "town", "city", "village", "county", "state",
                        ) if isinstance(components.get(key), str)),
                        name,
                    )
                    matches.append({
                        "name": name,
                        "area": area,
                        "latitude": latitude,
                        "longitude": longitude,
                    })
            if matches:
                return {"results": matches}
        except (httpx.HTTPError, ValueError):
            pass

    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": "Flingra/1.0 (location search)"},
            timeout=httpx.Timeout(5.0, connect=2.0),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailable("Location search is temporarily unavailable.") from exc

    matches = []
    seen = set()
    for item in payload:
        address = item.get("address") or {}
        name = item.get("display_name")
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        latitude = round(latitude, 6)
        longitude = round(longitude, 6)
        position = (latitude, longitude)
        if position in seen:
            continue
        seen.add(position)
        area = next(
            (address[key] for key in (
                "building", "amenity", "shop", "road", "quarter", "suburb",
                "neighbourhood", "city_district", "town", "city", "village",
                "municipality", "county", "state",
            ) if isinstance(address.get(key), str)),
            name,
        )
        if isinstance(name, str):
            matches.append({"name": name, "area": area, "latitude": latitude, "longitude": longitude})
    return {"results": matches}


@router.get("/reverse")
def reverse_geocode(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, str | None]:
    result: dict[str, object] | None = None
    if settings.opencage_api_key is not None:
        try:
            response = httpx.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={
                    "q": f"{latitude},{longitude}",
                    "key": settings.opencage_api_key.get_secret_value(),
                    "language": "en",
                    "no_annotations": "1",
                    "limit": "1",
                },
                timeout=httpx.Timeout(5.0, connect=2.0),
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            result = results[0] if results else None
        except (httpx.HTTPError, ValueError):
            result = None

    if result is None:
        try:
            response = httpx.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 18},
                headers={"User-Agent": "Flingra/1.0 (location lookup)"},
                timeout=httpx.Timeout(5.0, connect=2.0),
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailable("Location lookup is temporarily unavailable.") from exc

    components = result.get("components") or result.get("address") or {}
    if components.get("country_code") not in {None, "ng"}:
        return {"area": None}

    def first_component(*names: str) -> str | None:
        for name in names:
            value = components.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    area = first_component(
        "quarter",
        "neighbourhood",
        "neighborhood",
        "suburb",
        "city_district",
        "town",
        "city",
        "village",
        "municipality",
        "county",
        "state_district",
        "state",
    )
    city = first_component("city", "town", "village", "municipality", "county")
    state = first_component("state", "state_district")
    suffix = city or state
    if area and suffix and area.casefold() != suffix.casefold():
        area = f"{area}, {suffix}"
    return {"area": area}
