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
    __: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, str | None]:
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
    if area is None:
        for name_field in ("formatted", "display_name"):
            name = result.get(name_field)
            if isinstance(name, str) and name.strip():
                name_parts = [part.strip() for part in name.split(",") if part.strip()]
                country_index = next((i for i, part in enumerate(name_parts) if part.casefold() in {"nigeria", "ng"}), len(name_parts))
                useful_parts = name_parts[:country_index]
                if useful_parts:
                    area = useful_parts[-2] if len(useful_parts) >= 2 else useful_parts[0]
                    break
    city = first_component("city", "town", "village", "municipality", "county")
    state = first_component("state", "state_district")
    suffix = city or state
    if area and suffix and area.casefold() != suffix.casefold():
        area = f"{area}, {suffix}"
    return {"area": area}
