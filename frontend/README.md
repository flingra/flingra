# Frontend

This folder contains the frontend application code.

## Google Maps

The Discover page requires a Google Maps key. Configure it in the frontend
environment (for local development, create `frontend/.env`):

```
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_MAPS_API_KEY=your-key-here
VITE_GOOGLE_MAPS_MAP_ID=your-map-id-here
```

- `VITE_API_URL`: local FastAPI backend URL. Authentication uses this backend;
  other unfinished platform features still use the mock API layer.
- `VITE_GOOGLE_MAPS_API_KEY`: Google Cloud Console → APIs & Services → Credentials.
  Requires a billing account and the Maps JavaScript API enabled on the project.
  Restrict this browser key to the frontend website origins and Maps JavaScript API.
- `VITE_GOOGLE_MAPS_MAP_ID` (optional): Google Cloud Console → Maps → Map
  Management → create a map ID if you want to apply a cloud-based map style.

Onboarding maps use Google Maps. Place search and approximate reverse geocoding
are handled by the backend with a separate server-side key; configure
`FLINGRA_GOOGLE_MAPS_SERVER_API_KEY` in `backend/.env` and your production
backend environment. Enable Places API (New) and Geocoding API, keep the key
server-side, and restrict it to those APIs. Do not put this server key in a
`VITE_` variable. Restart `npm run dev` after changing local environment settings.
On mobile, Discover uses cooperative map gestures: one finger scrolls the page,
and two fingers pan or zoom the map.
Discover requests a fresh browser location when opened and uses it to center
the map and sort nearby profiles. This does not publish or save live location;
that remains a separate, opt-in action. If access is denied, Discover uses the
saved profile area when coordinates are available and lets the member search
for another area. The browser may remember a denied permission, which must be
changed in its site settings before it will ask again.

## Google sign-in

The backend's `FLINGRA_GOOGLE_CLIENT_ID` must be a Google OAuth Web client ID.
In Google Cloud Console, add the exact frontend origin (for example,
`https://dev.flingra.com`) under **Authorized JavaScript origins**. This is
separate from the Maps API key and from the backend CORS allow-list.
