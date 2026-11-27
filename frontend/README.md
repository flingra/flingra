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

## Vercel API routing

`vercel.json` forwards `/api/*` requests to the Render backend. Set
`VITE_API_URL` to `/api` in the Vercel deployments serving both
`dev.flingra.com` and `flingra.com`, then redeploy. Keep
`FLINGRA_ALLOWED_ORIGINS` on the backend set to the exact frontend origins,
for example `["https://dev.flingra.com","https://flingra.com"]`, for origin and
CSRF validation. Local development should continue using the direct backend
URL, such as `http://localhost:8000`.

Onboarding maps use Google Maps. Location search uses OpenStreetMap Nominatim
with Photon as a fallback and does not require a Google server key. Approximate
reverse geocoding optionally uses the backend's `FLINGRA_OPENCAGE_API_KEY` and
falls back to Nominatim. The browser Maps JavaScript key above is still required
to display interactive maps. Restart `npm run dev` after changing local
environment settings.
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
