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

GOOGLE_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_PLACES_FIELD_MASK = (
    "places.displayName,places.formattedAddress,places.location,places.addressComponents"
)

NIGERIA_COUNTRY_NAMES = frozenset({"ng", "nigeria"})
AREA_COMPONENT_TYPES = (
    "neighborhood",
    "sublocality_level_1",
    "sublocality",
    "locality",
    "administrative_area_level_2",
    "administrative_area_level_1",
)
CITY_COMPONENT_TYPES = ("locality", "postal_town", "administrative_area_level_2")
SEARCH_RESULT_LIMIT = 15
SEARCH_BIAS_RADIUS_M = 50_000.0  # Places API maximum

SEARCH_CACHE_TTL_S = 10 * 60
REVERSE_CACHE_TTL_S = 60 * 60
CACHE_MAX_ENTRIES = 512

logger = logging.getLogger("uvicorn.error")
# httpx logs full request URLs at INFO, and the Geocoding API only accepts its key as a
# query parameter. Keep it out of the logs.
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
# Tiny in-memory TTL/LRU cache (per process) to cut repeat Google calls
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


def _google_component_value(components: object, *component_types: str) -> str | None:
    """First non-empty name for the earliest matching type (handles Places and Geocoding shapes)."""
    if not isinstance(components, list):
        return None
    for component_type in component_types:
        for component in components:
            if not isinstance(component, dict):
                continue
            types = component.get("types")
            if not isinstance(types, list) or component_type not in types:
                continue
            value = (
                component.get("longText")
                or component.get("long_name")
                or component.get("shortText")
                or component.get("short_name")
            )
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _in_nigeria(components: object, *, allow_unknown: bool) -> bool:
    country = _google_component_value(components, "country")
    if country is None:
        return allow_unknown
    return country.casefold() in NIGERIA_COUNTRY_NAMES


def _format_area(components: object) -> str | None:
    """'Neighbourhood, City' when both exist and differ; otherwise the best single name."""
    area = _google_component_value(components, *AREA_COMPONENT_TYPES)
    city = _google_component_value(components, *CITY_COMPONENT_TYPES)
    suffix = city or _google_component_value(components, "administrative_area_level_1")
    if area and suffix and area.casefold() != suffix.casefold():
        return f"{area}, {suffix}"
    return area


def _google_maps_key(settings: Settings) -> str:
    if settings.google_maps_server_api_key is None:
        raise ServiceUnavailable("Google Maps location services are not configured.")
    return settings.google_maps_server_api_key.get_secret_value()


async def _google_json(
    method: str,
    url: str,
    *,
    service: str,
    unavailable_message: str,
    timeout: httpx.Timeout,
    **request_kwargs: Any,
) -> dict[str, Any]:
    """Call Google and return a JSON object, translating every failure into ServiceUnavailable."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, **request_kwargs)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = f"HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        detail = type(exc).__name__
    except ValueError:
        detail = "invalid JSON"
    else:
        if isinstance(payload, dict):
            return payload
        detail = "unexpected response shape"

    # Never log request params: they can contain the API key or user coordinates.
    logger.warning("%s failed: %s.", service, detail)
    raise ServiceUnavailable(unavailable_message)


def _coordinates(location: object) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    try:
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return round(latitude, 6), round(longitude, 6)


def _parse_place(place: object) -> LocationResult | None:
    if not isinstance(place, dict):
        return None
    components = place.get("addressComponents")
    if not _in_nigeria(components, allow_unknown=False):
        return None
    coordinates = _coordinates(place.get("location"))
    if coordinates is None:
        return None

    display_name = place.get("displayName")
    name = display_name.get("text") if isinstance(display_name, dict) else None
    if not isinstance(name, str) or not name.strip():
        name = place.get("formattedAddress")
    if not isinstance(name, str) or not name.strip():
        return None

    latitude, longitude = coordinates
    return LocationResult(
        name=name,
        area=_google_component_value(components, *AREA_COMPONENT_TYPES) or name,
        latitude=latitude,
        longitude=longitude,
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/search", response_model=LocationSearchResponse)
async def search_locations(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    q: str = Query(min_length=2, max_length=120),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
) -> LocationSearchResponse:
    """Search Nigerian places. Optional latitude/longitude bias results toward the caller."""
    key = _google_maps_key(settings)

    text = " ".join(q.split())
    if len(text) < 2:
        return LocationSearchResponse(results=[])
    search_query = text if "nigeria" in text.casefold() else f"{text}, Nigeria"

    bias = (round(latitude, 2), round(longitude, 2)) if latitude is not None and longitude is not None else None
    cache_key = (search_query.casefold(), bias)
    cached = _search_cache.get(cache_key)
    if cached is not _MISS:
        return LocationSearchResponse(results=cached)

    body: dict[str, Any] = {
        "textQuery": search_query,
        "languageCode": "en",
        "regionCode": "NG",
        "maxResultCount": SEARCH_RESULT_LIMIT,
    }
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": SEARCH_BIAS_RADIUS_M,
            }
        }

    payload = await _google_json(
        "POST",
        GOOGLE_PLACES_SEARCH_URL,
        service="Google Places search",
        unavailable_message="Google Maps location search is temporarily unavailable.",
        timeout=httpx.Timeout(10.0, connect=3.0),
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
            "Content-Type": "application/json",
        },
        json=body,
    )
    places = payload.get("places", [])
    if not isinstance(places, list):
        logger.warning("Google Places search failed: unexpected places shape.")
        raise ServiceUnavailable("Google Maps location search is temporarily unavailable.")

    results: list[LocationResult] = []
    seen: set[tuple[float, float]] = set()
    for place in places:
        match = _parse_place(place)
        if match is None:
            continue
        position = (match.latitude, match.longitude)
        if position in seen:
            continue
        seen.add(position)
        results.append(match)

    _search_cache.set(cache_key, results)
    return LocationSearchResponse(results=results)


@router.get("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> ReverseGeocodeResponse:
    """Neighbourhood-level area name for a coordinate. Cached at roughly 100 m resolution."""
    key = _google_maps_key(settings)

    cache_key = (round(latitude, 3), round(longitude, 3))
    cached = _reverse_cache.get(cache_key)
    if cached is not _MISS:
        return ReverseGeocodeResponse(area=cached)

    payload = await _google_json(
        "GET",
        GOOGLE_GEOCODING_URL,
        service="Google Geocoding",
        unavailable_message="Google Maps location lookup is temporarily unavailable.",
        timeout=httpx.Timeout(5.0, connect=2.0),
        params={
            "latlng": f"{latitude},{longitude}",
            "key": key,
            "language": "en",
            "region": "ng",
        },
    )

    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        logger.warning("Google Geocoding returned status %s.", status)
        raise ServiceUnavailable("Google Maps location lookup is temporarily unavailable.")

    area: str | None = None
    results = payload.get("results")
    if status == "OK" and isinstance(results, list) and results and isinstance(results[0], dict):
        components = results[0].get("address_components")
        if _in_nigeria(components, allow_unknown=True):
            area = _format_area(components)

    _reverse_cache.set(cache_key, area)
    return ReverseGeocodeResponse(area=area)