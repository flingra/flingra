# Frontend

This folder contains the frontend application code.

## Live Google map (optional)

The Discover page map works out of the box with a built-in stylized map (no setup
needed). To switch it to a real, interactive Google map, create
`frontend/.env` with:

```
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_MAPS_API_KEY=your-key-here
VITE_GOOGLE_MAPS_MAP_ID=your-map-id-here
```

- `VITE_API_URL`: local FastAPI backend URL. Authentication uses this backend;
  other unfinished platform features still use the mock API layer.
- `VITE_GOOGLE_MAPS_API_KEY`: Google Cloud Console → APIs & Services → Credentials.
  Requires a billing account and the Maps JavaScript API enabled on the project.
- `VITE_GOOGLE_MAPS_MAP_ID` (optional): Google Cloud Console → Maps → Map
  Management → create a map with render type **Vector**. Required for the
  tilted 45° "3D" buildings view — without it the map still loads with pins,
  just flat.

Restart `npm run dev` after adding the file.
