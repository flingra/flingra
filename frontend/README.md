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
  Restrict the key to the frontend website origin.
- `VITE_GOOGLE_MAPS_MAP_ID` (optional): Google Cloud Console → Maps → Map
  Management → create a map with render type **Vector**. Required for the
  tilted 45° "3D" buildings view — without it the map still loads with pins,
  just flat.

The onboarding location picker retains its OpenStreetMap fallback. Restart
`npm run dev` after changing local environment settings.

## Google sign-in

The backend's `FLINGRA_GOOGLE_CLIENT_ID` must be a Google OAuth Web client ID.
In Google Cloud Console, add the exact frontend origin (for example,
`https://dev.flingra.com`) under **Authorized JavaScript origins**. This is
separate from the Maps API key and from the backend CORS allow-list.
