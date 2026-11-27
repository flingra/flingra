import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.errors import ServiceUnavailable
from app.routes.auth import CurrentAccount, get_app_settings

router = APIRouter(prefix="/location", tags=["location"])
GOOGLE_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_PLACES_FIELD_MASK = (
    "places.displayName,places.formattedAddress,places.location,places.addressComponents"
)
logger = logging.getLogger("uvicorn.error")


def _google_component_value(components: object, *component_types: str) -> str | None:
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


def _google_maps_key(settings: Settings) -> str:
    if settings.google_maps_server_api_key is None:
        raise ServiceUnavailable("Google Maps location services are not configured.")
    return settings.google_maps_server_api_key.get_secret_value()


@router.get("/search")
def search_locations(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    q: str = Query(min_length=2, max_length=120),
) -> dict[str, list[dict[str, str | float]]]:
    search_query = q if "nigeria" in q.casefold() else f"{q}, Nigeria"
    key = _google_maps_key(settings)
    try:
        response = httpx.post(
            GOOGLE_PLACES_SEARCH_URL,
            headers={
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
                "Content-Type": "application/json",
            },
            json={
                "textQuery": search_query,
                "languageCode": "en",
                "regionCode": "NG",
                "maxResultCount": 15,
            },
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("places", []), list):
            raise ValueError("Google Places returned an invalid response")
    except httpx.HTTPStatusError as exc:
        logger.warning("Google Places search returned HTTP %d.", exc.response.status_code)
        raise ServiceUnavailable("Google Maps location search is temporarily unavailable.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Google Places search failed (%s).", type(exc).__name__)
        raise ServiceUnavailable("Google Maps location search is temporarily unavailable.") from exc
    except ValueError as exc:
        logger.warning("Google Places search returned invalid JSON.")
        raise ServiceUnavailable("Google Maps location search is temporarily unavailable.") from exc

    matches = []
    seen = set()
    for place in payload.get("places", []):
        if not isinstance(place, dict):
            continue
        components = place.get("addressComponents")
        country = _google_component_value(components, "country")
        if country is None or country.casefold() not in {"ng", "nigeria"}:
            continue
        location = place.get("location")
        if not isinstance(location, dict):
            continue
        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        latitude = round(latitude, 6)
        longitude = round(longitude, 6)
        position = (latitude, longitude)
        if position in seen:
            continue
        seen.add(position)
        area = _google_component_value(
            components,
            "neighborhood",
            "sublocality_level_1",
            "sublocality",
            "locality",
            "administrative_area_level_2",
            "administrative_area_level_1",
        )
        display_name = place.get("displayName")
        name = display_name.get("text") if isinstance(display_name, dict) else None
        if not isinstance(name, str):
            name = place.get("formattedAddress")
        if isinstance(name, str):
            matches.append(
                {
                    "name": name,
                    "area": area or name,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
    return {"results": matches}


@router.get("/reverse")
def reverse_geocode(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, str | None]:
    key = _google_maps_key(settings)
    try:
        response = httpx.get(
            GOOGLE_GEOCODING_URL,
            params={
                "latlng": f"{latitude},{longitude}",
                "key": key,
                "language": "en",
                "region": "ng",
            },
            timeout=httpx.Timeout(5.0, connect=2.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Google Geocoding returned an invalid response")
    except httpx.HTTPStatusError as exc:
        logger.warning("Google Geocoding returned HTTP %d.", exc.response.status_code)
        raise ServiceUnavailable("Google Maps location lookup is temporarily unavailable.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Google Geocoding failed (%s).", type(exc).__name__)
        raise ServiceUnavailable("Google Maps location lookup is temporarily unavailable.") from exc
    except ValueError as exc:
        logger.warning("Google Geocoding returned invalid JSON.")
        raise ServiceUnavailable("Google Maps location lookup is temporarily unavailable.") from exc

    status = payload.get("status")
    if status == "ZERO_RESULTS":
        return {"area": None}
    if status != "OK":
        logger.warning("Google Geocoding returned status %s.", status)
        raise ServiceUnavailable("Google Maps location lookup is temporarily unavailable.")

    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return {"area": None}

    components = results[0].get("address_components")
    country = _google_component_value(components, "country")
    if country is not None and country.casefold() not in {"ng", "nigeria"}:
        return {"area": None}
    area = _google_component_value(
        components,
        "neighborhood",
        "sublocality_level_1",
        "sublocality",
        "locality",
        "administrative_area_level_2",
        "administrative_area_level_1",
    )
    city = _google_component_value(
        components,
        "locality",
        "postal_town",
        "administrative_area_level_2",
    )
    state = _google_component_value(components, "administrative_area_level_1")
    suffix = city or state
    if area and suffix and area.casefold() != suffix.casefold():
        area = f"{area}, {suffix}"
    return {"area": area}
