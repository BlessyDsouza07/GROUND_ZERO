/**
 * Thin fetch wrapper around Layer 3 (Context Engine / Silence Filter / Ask
 * Engine — mounted at /l3 by main.py) and the Live Mangaluru Events module
 * (mounted at /events-live). Same BASE_URL and request() pattern as
 * client.js — see that file's header for the LAN-IP note when testing on
 * a physical device with Expo.
 */
export const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body}`);
  }
  return response.json();
}

export const Layer3Api = {
  // itinerary: the exact queue/items HiveResultsScreen already has (each
  // needs at least place_id + role — see layer3/layer3_bridge.py's
  // normalize_itinerary(), which is deliberately tolerant of shape).
  startSession: (profileId, itinerary, { language, voice, groupSessionId, walletRemaining } = {}) =>
    request("/l3/session/start", {
      method: "POST",
      body: JSON.stringify({
        profile_id: profileId,
        itinerary,
        language,
        voice,
        group_session_id: groupSessionId,
        wallet_remaining: walletRemaining,
      }),
    }),

  getSession: (sessionId) => request(`/l3/session/${sessionId}`),

  updateState: (sessionId, patch) =>
    request(`/l3/session/${sessionId}/state`, { method: "PUT", body: JSON.stringify(patch) }),

  ping: (sessionId, lat, lng, extra = {}) =>
    request("/l3/location/ping", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, lat, lng, ...extra }),
    }),

  // THE decision — call this after every ping (or on "I'm here"/manual_trigger).
  evaluate: (sessionId, lat, lng, { manualTrigger = false, targetPlaceId, energyBand } = {}) =>
    request("/l3/context/evaluate", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        lat,
        lng,
        manual_trigger: manualTrigger,
        target_place_id: targetPlaceId,
        energy_band: energyBand,
      }),
    }),

  conditions: (lat, lng, placeId) =>
    request(`/l3/conditions?lat=${lat}&lng=${lng}${placeId ? `&place_id=${placeId}` : ""}`),

  dismissNotification: (sessionId, notificationId) =>
    request("/l3/notify/dismiss", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, notification_id: notificationId }),
    }),

  engageNotification: (sessionId, notificationId, action = "tapped") =>
    request("/l3/notify/engage", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, notification_id: notificationId, action }),
    }),

  tellMore: (sessionId, { notificationId, placeId, language } = {}) =>
    request("/l3/notify/tell-more", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, notification_id: notificationId, place_id: placeId, language }),
    }),

  // Ask Engine — answers ONLY from the place's own stored record (+ live
  // data for "right now" questions). session_id/place_id/lat/lng are all
  // optional — omit place_id to let it infer from the session's current slot.
  ask: (question, { sessionId, placeId, language, lat, lng } = {}) =>
    request("/l3/ask", {
      method: "POST",
      body: JSON.stringify({ question, session_id: sessionId, place_id: placeId, language, lat, lng }),
    }),

  setQuietHours: (sessionId, minutes) =>
    request("/l3/quiet", { method: "POST", body: JSON.stringify({ session_id: sessionId, minutes }) }),

  sos: (sessionId, lat, lng) =>
    request("/l3/sos", { method: "POST", body: JSON.stringify({ session_id: sessionId, lat, lng }) }),

  clearSos: (sessionId) => request("/l3/sos/clear", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }),

  recordVisit: (sessionId, placeId, { dwellMinutes, satisfaction } = {}) =>
    request("/l3/visit", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        place_id: placeId,
        dwell_minutes: dwellMinutes,
        satisfaction,
      }),
    }),
};

export const EventsApi = {
  // Verified, public, physical, itinerary-eligible events only — see
  // live_events/docs/DATA_POLICY.md for the exact gate. May legitimately
  // be empty (no fabricated events, ever) — screens should treat [] as a
  // normal, expected answer, not an error state.
  itinerarySafe: (days) => request(`/events-live/events/itinerary-safe${days ? `?days=${days}` : ""}`),
  today: () => request("/events-live/events/today"),
};
