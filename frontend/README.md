# Frontend

This folder contains the frontend application code.

## Live Google map (optional)

The Discover page map works out of the box with a built-in stylized map (no setup
needed). To switch it to a real, interactive Google map, create
`frontend/.env.local` with:

```
VITE_GOOGLE_MAPS_API_KEY=your-key-here
VITE_GOOGLE_MAPS_MAP_ID=your-map-id-here
```

- `VITE_GOOGLE_MAPS_API_KEY`: Google Cloud Console → APIs & Services → Credentials.
  Requires a billing account and the Maps JavaScript API enabled on the project.
- `VITE_GOOGLE_MAPS_MAP_ID` (optional): Google Cloud Console → Maps → Map
  Management → create a map with render type **Vector**. Required for the
  tilted 45° "3D" buildings view — without it the map still loads with pins,
  just flat.

Restart `npm run dev` after adding the file.
