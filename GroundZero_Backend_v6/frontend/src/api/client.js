/**
 * Thin fetch wrapper around the Ground Zero backend (main.py, mounting
 * Layer 0/1/2/3/5 routers + the Live Events module).
 *
 * BASE_URL — the #1 cause of "Failed to fetch": on web or an iOS
 * Simulator, "http://localhost:8000" reaches your dev machine fine. On a
 * PHYSICAL PHONE via Expo Go, or most Android emulators, "localhost"
 * means the phone/emulator itself — nothing is listening on its own port
 * 8000, so every request fails with exactly this error. Fix: set
 * EXPO_PUBLIC_API_BASE_URL in frontend/.env to your computer's actual LAN
 * IP (Mac/Linux: `ifconfig | grep inet`; Windows: `ipconfig` — look for
 * something like 192.168.x.x or 10.x.x.x), e.g.
 * EXPO_PUBLIC_API_BASE_URL=http://192.168.1.42:8000, then fully restart
 * `npx expo start` (env vars are read at bundle time, a hot reload is not
 * enough). Your phone and computer must be on the same Wi-Fi network.
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

export const SurveyApi = {
  start: (deviceId, joinGroupSessionId) =>
    request("/survey/start", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, join_group_session_id: joinGroupSessionId }),
    }),
  getState: (sessionId) => request(`/survey/${sessionId}`),
  answer: (sessionId, answer) =>
    request(`/survey/${sessionId}/answer`, { method: "POST", body: JSON.stringify({ answer }) }),
  finalize: (sessionId) => request(`/survey/${sessionId}/finalize`, { method: "POST" }),
  getGroupMembers: (groupSessionId) => request(`/survey/group/${groupSessionId}/members`),
};

export const HiveApi = {
  getRecommendations: (profileId, startTime, startLatitude, startLongitude) =>
    request("/hive/recommendations", {
      method: "POST",
      body: JSON.stringify({
        profile_id: profileId,
        start_time: startTime,
        start_latitude: startLatitude,
        start_longitude: startLongitude,
      }),
    }),
};

export const ItineraryApi = {
  get: (profileId) => request(`/hive/itinerary/${profileId}`),
  save: (profileId, { items, removedPlaceIds = [], addedPlaceIds = [], placeRatings = {}, overallRating = null }) =>
    request(`/hive/itinerary/${profileId}/save`, {
      method: "POST",
      body: JSON.stringify({
        items,
        removed_place_ids: removedPlaceIds,
        added_place_ids: addedPlaceIds,
        place_ratings: placeRatings,
        overall_rating: overallRating,
      }),
    }),
  confirm: (profileId) => request(`/hive/itinerary/${profileId}/confirm`, { method: "POST" }),
};

export const PlacesApi = {
  list: (category) => request(`/places${category ? `?category=${category}` : ""}`),
  get: (placeId) => request(`/places/${placeId}`),
  submit: (place) => request("/places/submissions", { method: "POST", body: JSON.stringify(place) }),
};
