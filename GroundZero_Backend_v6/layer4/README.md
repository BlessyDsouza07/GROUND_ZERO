# Layer 4 — Live Guidance

Layer 4 is the live-trip supervisor used by the combined `main.py` app.

## Runtime flow

1. `POST /l3/session/start` creates an active session.
2. The combined app starts a Layer 4 supervisor task for that session.
3. The mobile map tracks GPS with Expo Location.
4. `POST /layer4/navigation/route` sends the current position plus the remaining HIVE queue to OSM/OSRM.
5. Queue order is preserved: first pending slot, then the next. A depth-first priority traversal keeps that order, while OSRM supplies the shortest road-network path for the current ordered waypoint chain.
6. The frontend reroutes periodically as the user's position changes.
7. If both free routing endpoints fail, Layer 4 returns a transparent haversine fallback with `routed=false`.
8. Paused, completed, and ended sessions stop the supervisor; resume starts it again.

## API

- `POST /layer4/navigation/route`
- `GET /layer4/session/{session_id}`

No API key is required for the public OSM/OSRM endpoints. For production traffic, configure `LAYER4_OSRM_BASE_URL` to a self-hosted routing service.
