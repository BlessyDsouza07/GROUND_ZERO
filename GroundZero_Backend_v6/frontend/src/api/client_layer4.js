import { BASE_URL } from "./client";

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

export const Layer4Api = {
  route: (origin, waypoints) =>
    request("/layer4/navigation/route", {
      method: "POST",
      body: JSON.stringify({
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        waypoints: waypoints.map((w, index) => ({
          place_id: w.place_id,
          place_name: w.place_name,
          lat: w.lat,
          lng: w.lng,
          status: w.status || "pending",
          role: w.role,
          priority: index,
        })),
      }),
    }),
  session: (sessionId) => request(`/layer4/session/${sessionId}`),
};
