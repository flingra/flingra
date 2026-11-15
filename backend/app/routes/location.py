from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.errors import ServiceUnavailable
from app.routes.auth import CurrentAccount, get_app_settings

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/reverse")
def reverse_geocode(
    _: CurrentAccount,
    settings: Annotated[Settings, Depends(get_app_settings)],
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, str | None]:
    if settings.opencage_api_key is None:
        raise ServiceUnavailable("Location lookup is not configured on the server.")

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
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailable("Location lookup is temporarily unavailable.") from exc

    components = result.get("results", [{}])[0].get("components", {})
    area = (
        components.get("suburb")
        or components.get("neighbourhood")
        or components.get("town")
        or components.get("city")
        or components.get("village")
    )
    city = components.get("city") or components.get("town") or components.get("village")
    state = components.get("state")
    suffix = city or state
    if area and suffix and area != suffix:
        area = f"{area}, {suffix}"
    return {"area": area}
