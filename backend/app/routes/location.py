from __future__ import annotations

import logging
import math
import time
from collections import OrderedDict
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.config import Settings
from app.errors import ServiceUnavailable
from app.routes.auth import CurrentAccount, get_app_settings

router = APIRouter(prefix="/location", tags=["location"])

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api"
OPENCAGE_REVERSE_URL = "https://api.opencagedata.com/geocode/v1/json"
NOMINATIM_USER_AGENT = "Flingra/1.0 (+https://dev.flingra.com)"
SEARCH_RESULT_LIMIT = 15

SEARCH_CACHE_TTL_S = 10 * 60
REVERSE_CACHE_TTL_S = 60 * 60
CACHE_MAX_ENTRIES = 512

logger = logging.getLogger("uvicorn.error")
# OpenCage keys are query parameters; keep them out of HTTP request logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


class LocationResult(BaseModel):
    name: str
    area: str
    latitude: float
    longitude: float


class LocationSearchResponse(BaseModel):
    results: list[LocationResult]


class ReverseGeocodeResponse(BaseModel):
    area: str | None


# --------------------------------------------------------------------------- #
# Tiny in-memory TTL/LRU cache (per process) to reduce repeat provider calls
# --------------------------------------------------------------------------- #

_MISS = object()


class _TTLCache:
    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        self._items: OrderedDict[object, tuple[float, Any]] = OrderedDict()
        self._max_entries = max_entries
        self._ttl = ttl_seconds

    def get(self, key: object) -> Any:
        entry = self._items.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if expires_at < time.monotonic():
            del self._items[key]
            return _MISS
        self._items.move_to_end(key)
        return value

    def set(self, key: object, value: Any) -> None:
        self._items[key] = (time.monotonic() + self._ttl, value)
        self._items.move_to_end(key)
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)


_search_cache = _TTLCache(max_entries=CACHE_MAX_ENTRIES, ttl_seconds=SEARCH_CACHE_TTL_S)
_reverse_cache = _TTLCache(max_entries=CACHE_MAX_ENTRIES, ttl_seconds=REVERSE_CACHE_TTL_S)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _provider_json(
    url: str,
    *,
    service: str,
    timeout: httpx.Timeout,
    params: dict[str, str | int | float],
    headers: dict[str, str] | None = None,
) -> object | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("%s returned HTTP %d.", service, exc.response.status_code)
        return None
    except httpx.HTTPError as exc:
        logger.warning("%s failed (%s).", service, type(exc).__name__)
        return None
    try:
        return response.json()
    except ValueError:
        logger.warning("%s returned invalid JSON.", service)
        return None


def _coordinates(latitude: object, longitude: object) -> tuple[float, float] | None:
    try:
        latitude_value = float(latitude)
        longitude_value = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude_value) and math.isfinite(longitude_value)):
        return None
    if not (-90 <= latitude_value <= 90 and -180 <= longitude_value <= 180):
        return None
    return round(latitude_value, 6), round(longitude_value, 6)


def _first_string(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_search_results(payload: object) -> list[LocationResult]:
    if not isinstance(payload, list):
        raise ServiceUnavailable("Location search is temporarily unavailable.")
    results: list[LocationResult] = []
    seen: set[tuple[float, float]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        coordinates = _coordinates(item.get("lat"), item.get("lon"))
        name = item.get("display_name")
        address = item.get("address")
        if coordinates is None or not isinstance(name, str) or not name.strip():
            continue
        address = address if isinstance(address, dict) else {}
        area = _first_string(
            address,
            "area",
            "building",
            "park",
            "amenity",
            "shop",
            "road",
            "quarter",
            "suburb",
            "neighbourhood",
            "neighborhood",
            "city_district",
            "town",
            "city",
            "village",
            "municipality",
            "county",
            "state",
        )
        position = coordinates
        if position in seen:
            continue
        seen.add(position)
        results.append(
            LocationResult(
                name=name.strip(),
                area=area or name.strip(),
                latitude=coordinates[0],
                longitude=coordinates[1],
            )
        )
    return results


def _photon_results(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ServiceUnavailable("Location search is temporarily unavailable.")
    results: list[dict[str, Any]] = []
    for feature in payload["features"]:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue
        country = properties.get("country")
        if country not in {None, "Nigeria"}:
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        position = _coordinates(coordinates[1], coordinates[0])
        if position is None:
            continue
        area = _first_string(
            properties,
            "name",
            "district",
            "suburb",
            "neighbourhood",
            "city",
            "county",
            "state",
        )
        if area is None:
            continue
        name_parts = [
            properties[key]
            for key in ("name", "street", "district", "suburb", "city", "state", "country")
            if isinstance(properties.get(key), str) and properties[key].strip()
        ]
        results.append(
            {
                "display_name": ", ".join(dict.fromkeys(name_parts)),
                "lat": position[0],
                "lon": position[1],
                "address": {"area": area},
            }
        )
    return results


def _place_area(components: object) -> str | None:
    if not isinstance(components, dict):
        return None
    country = components.get("country_code")
    if country not in {None, "ng"}:
        return None
    area = _first_string(
        components,
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
        for field in ("formatted", "display_name"):
            name = components.get(field)
            if isinstance(name, str) and name.strip():
                parts = [part.strip() for part in name.split(",") if part.strip()]
                country_index = next(
                    (
                        index
                        for index, part in enumerate(parts)
                        if part.casefold() in {"nigeria", "ng"}
                    ),
                    len(parts),
                )
                useful_parts = parts[:country_index]
                if useful_parts:
                    area = useful_parts[-2] if len(useful_parts) >= 2 else useful_parts[0]
                    break
    if area is None:
        return None
    city = _first_string(components, "city", "town", "village", "municipality", "county")
    state = _first_string(components, "state", "state_district")
    suffix = city or state
    if suffix and area.casefold() != suffix.casefold():
        return f"{area}, {suffix}"
    return area


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/search", response_model=LocationSearchResponse)
async def search_locations(
    _: CurrentAccount,
    q: str = Query(min_length=2, max_length=120),
) -> LocationSearchResponse:
    """Search Nigerian places using Nominatim, with Photon as a fallback."""
    text = " ".join(q.split())
    if len(text) < 2:
        return LocationSearchResponse(results=[])
    search_query = text if "nigeria" in text.casefold() else f"{text}, Nigeria"
    cache_key = search_query.casefold()
    cached = _search_cache.get(cache_key)
    if cached is not _MISS:
        return LocationSearchResponse(results=cached)

    params: dict[str, str | int | float] = {
        "q": search_query,
        "format": "jsonv2",
        "limit": SEARCH_RESULT_LIMIT,
        "countrycodes": "ng",
        "addressdetails": 1,
        "dedupe": 1,
        "namedetails": 1,
    }
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    payload = await _provider_json(
        NOMINATIM_SEARCH_URL,
        service="Nominatim search",
        timeout=httpx.Timeout(10.0, connect=3.0),
        params=params,
        headers=headers,
    )
    if not isinstance(payload, list):
        photon_payload = await _provider_json(
            PHOTON_SEARCH_URL,
            service="Photon search",
            timeout=httpx.Timeout(10.0, connect=3.0),
            params={"q": search_query, "limit": SEARCH_RESULT_LIMIT, "lang": "en"},
            headers=headers,
        )
        raw_results = _photon_results(photon_payload)
    else:
        raw_results = payload
    results = _parse_search_results(raw_results)
    _search_cache.set(cache_key, results)
    return LocationSearchResponse(results=results)


@router.get("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> ReverseGeocodeResponse:
    """Resolve an approximate area with OpenCage, falling back to Nominatim."""
    cache_key = (round(latitude, 3), round(longitude, 3))
    cached = _reverse_cache.get(cache_key)
    if cached is not _MISS:
        return ReverseGeocodeResponse(area=cached)

    area: str | None = None
    if settings.opencage_api_key is not None:
        payload = await _provider_json(
            OPENCAGE_REVERSE_URL,
            service="OpenCage reverse geocoding",
            timeout=httpx.Timeout(5.0, connect=2.0),
            params={
                "q": f"{latitude},{longitude}",
                "key": settings.opencage_api_key.get_secret_value(),
                "no_annotations": 1,
                "limit": 1,
            },
        )
        if isinstance(payload, dict):
            results = payload.get("results")
            if isinstance(results, list) and results and isinstance(results[0], dict):
                components = results[0].get("components")
                if isinstance(components, dict):
                    area = _place_area(components)

    if area is None:
        payload = await _provider_json(
            NOMINATIM_REVERSE_URL,
            service="Nominatim reverse geocoding",
            timeout=httpx.Timeout(5.0, connect=2.0),
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": 18,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
        )
        if not isinstance(payload, dict):
            raise ServiceUnavailable("Location lookup is temporarily unavailable.")
        address = payload.get("address")
        if isinstance(address, dict):
            area = _place_area(address)

    _reverse_cache.set(cache_key, area)
    return ReverseGeocodeResponse(area=area)