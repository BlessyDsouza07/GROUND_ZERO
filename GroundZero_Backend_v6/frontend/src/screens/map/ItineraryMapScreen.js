import React, { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Linking, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import * as Location from "expo-location";
import { PlacesApi } from "../../api/client";
import { Layer4Api } from "../../api/client_layer4";
import { colors, radii, spacing, typography } from "../../theme/tokens";

const WebView = Platform.OS === "web" ? null : require("react-native-webview").WebView;
const REROUTE_MS = 12_000;

// Real turn-by-turn, with live traffic, is a job for the phone's own Maps
// app (Google Maps / Apple Maps) — no free embeddable router matches that.
// This screen keeps the in-app OSM overview + live "you are here" dot for
// the whole trip, and "Navigate" hands off the current leg to Maps, which
// opens in its own tab/app exactly the way a person already expects.
function openInMapsApp(target) {
  if (!target) return;
  const webUrl = `https://www.google.com/maps/dir/?api=1&destination=${target.lat},${target.lng}&travelmode=driving`;
  const url = Platform.select({
    ios: `maps:0,0?q=${target.lat},${target.lng}`,
    android: `geo:0,0?q=${target.lat},${target.lng}(${encodeURIComponent(target.name || "Destination")})`,
    default: webUrl,
  });
  Linking.openURL(url).catch(() => Linking.openURL(webUrl));
}

export default function ItineraryMapScreen({ itinerary = [], queue = [], onClose }) {
  const [points, setPoints] = useState(null);
  const [current, setCurrent] = useState(null);
  const [route, setRoute] = useState(null);
  const [error, setError] = useState(null);
  const [tracking, setTracking] = useState(false);
  const watchRef = useRef(null);

  const placeIds = useMemo(() => Array.from(new Set((itinerary || []).map((i) => i.place_id).filter(Boolean))), [itinerary]);
  const statusByPlace = useMemo(() => {
    const m = {};
    (queue || []).forEach((s) => { if (s.place_id) m[s.place_id] = s.status; });
    return m;
  }, [queue]);

  useEffect(() => {
    if (!placeIds.length) { setError("No stops to show yet."); return undefined; }
    let cancelled = false;
    Promise.all(placeIds.map((id) => PlacesApi.get(id).catch(() => null))).then((results) => {
      if (cancelled) return;
      const pts = results.map((p, i) => p && p.latitude != null && p.longitude != null ? {
        id: placeIds[i], name: p.name || placeIds[i], lat: p.latitude, lng: p.longitude,
        status: statusByPlace[placeIds[i]] || "pending",
      } : null).filter(Boolean);
      if (!pts.length) setError("Couldn't find coordinates for this itinerary yet.");
      else setPoints(pts);
    }).catch(() => setError("Couldn't load route points."));
    return () => { cancelled = true; };
  }, [placeIds, statusByPlace]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== "granted") {
          setError((prev) => prev || "Location permission is needed for live guidance; the planned route can still be viewed.");
          return;
        }
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        if (!cancelled) setCurrent({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy });
        setTracking(true);
        watchRef.current = await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.High, distanceInterval: 8, timeInterval: 5000 },
          (pos2) => setCurrent({ lat: pos2.coords.latitude, lng: pos2.coords.longitude, accuracy: pos2.coords.accuracy })
        );
      } catch {
        if (!cancelled) setTracking(false);
      }
    })();
    return () => { cancelled = true; watchRef.current?.remove?.(); };
  }, []);

  const pendingWaypoints = useMemo(() => {
    if (!points) return [];
    const ranked = (queue || []).filter((s) => !["visited", "skipped", "dropped", "replaced"].includes(s.status));
    const byId = new Map(points.map((p) => [p.id, p]));
    // Preserve the HIVE priority exactly: first pending slot, then next.
    const ordered = ranked.map((s) => byId.get(s.place_id)).filter(Boolean);
    return (ordered.length ? ordered : points).map((p) => ({ ...p, role: (queue.find((q) => q.place_id === p.id) || {}).role }));
  }, [points, queue]);

  useEffect(() => {
    if (!current || !pendingWaypoints.length) return undefined;
    let cancelled = false;
    const refresh = () => Layer4Api.route(current, pendingWaypoints).then((r) => {
      if (!cancelled) setRoute(r);
    }).catch(() => {});
    refresh();
    const timer = setInterval(refresh, REROUTE_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [current?.lat, current?.lng, pendingWaypoints.map((p) => p.id).join(",")]);

  if (error && !points) return <View style={styles.center}><Text style={styles.msg}>{error}</Text>{onClose && <Pressable onPress={onClose} style={styles.backBtn}><Text style={styles.backText}>← Back</Text></Pressable>}</View>;
  if (!points) return <View style={styles.center}><ActivityIndicator color={colors.brass} /><Text style={styles.msg}>Loading your places…</Text></View>;

  const next = pendingWaypoints[0];
  const firstLeg = route?.legs?.[0];
  const distanceKm = firstLeg?.distance != null ? (firstLeg.distance / 1000).toFixed(1) : null;
  const etaMin = firstLeg?.duration != null ? Math.max(1, Math.round(firstLeg.duration / 60)) : null;
  const firstStep = firstLeg?.steps?.[0];
  const instruction = firstStep ? formatStep(firstStep) : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.heading}>Live route</Text>
          <Text style={styles.subheading}>{tracking ? "Tracking your location" : "Planned route"}</Text>
        </View>
        {onClose && <Pressable onPress={onClose}><Text style={styles.backText}>Close ✕</Text></Pressable>}
      </View>

      <View style={styles.statusCard}>
        <View style={styles.pin}><Text style={styles.pinText}>●</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.youAreHere}>YOU ARE HERE</Text>
          <Text style={styles.nextName}>{next ? `Next: ${next.name}` : "All planned stops resolved"}</Text>
          {distanceKm && etaMin != null && <Text style={styles.routeMeta}>{distanceKm} km · about {etaMin} min · {route?.routed ? "OSM shortest road route" : "offline estimate"}</Text>}
          {instruction && <Text style={styles.instruction}>{instruction}</Text>}
        </View>
      </View>

      {error && <Text style={styles.warning}>{error}</Text>}
      <MapFrame points={points} current={current} route={route} />
      <View style={styles.mapActions}>
        <Pressable
          onPress={() => openInMapsApp(next)}
          style={styles.navigateButton}
          disabled={!pendingWaypoints.length}
        >
          <Text style={styles.navigateButtonText}>{"🧭 Navigate with live traffic"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function formatStep(step) {
  const m = step?.maneuver || {};
  const action = { turn: "Turn", merge: "Merge", depart: "Start", arrive: "Arrive", roundabout: "Enter roundabout", fork: "Keep", new_name: "Continue", continue: "Continue" }[m.type] || "Continue";
  const modifier = m.modifier ? ` ${m.modifier.replace("-", " ")}` : "";
  const road = step.name ? ` onto ${step.name}` : "";
  return `${action}${modifier}${road}`;
}

function MapFrame({ points, current, route }) {
  const nativeRef = useRef(null);
  const iframeRef = useRef(null);
  const html = useMemo(() => buildLeafletHtml(points), [points]);

  useEffect(() => {
    const payload = JSON.stringify({ current, route });
    if (Platform.OS === "web") {
      iframeRef.current?.contentWindow?.postMessage({ type: "groundzero-update", current, route }, "*");
    } else {
      nativeRef.current?.injectJavaScript("window.updateGroundZero(" + payload + "); true;");
    }
  }, [current, route]);

  if (Platform.OS === "web") {
    return <iframe ref={iframeRef} srcDoc={html} style={{ border: 0, width: "100%", flex: 1 }} title="Live OSM route" />;
  }
  return <WebView ref={nativeRef} originWhitelist={["*"]} source={{ html }} style={styles.map} geolocationEnabled />;
}

function buildLeafletHtml(points) {
  const markers = points.map((p, i) => `L.marker([${p.lat},${p.lng}]).addTo(map).bindPopup(${JSON.stringify(`${i + 1}. ${p.name}`)});`).join("\n");
  const initial = JSON.stringify(points.map((p) => [p.lat, p.lng]));
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"/><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><style>html,body,#map{height:100%;margin:0;background:#0b1e1c}.leaflet-control-attribution{font-size:9px}.gz-recenter{position:absolute;right:10px;top:10px;z-index:1000;background:rgba(11,30,28,0.92);color:#f3ead9;border:1px solid rgba(201,143,74,0.5);border-radius:8px;width:36px;height:36px;line-height:36px;text-align:center;font-size:18px;}</style></head><body><div id="map"></div><div class="gz-recenter" id="recenter">◎</div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
var map=L.map('map');L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(map);
var pts=${initial};${markers}
var here=null,routeLine=null,followMe=true;var bounds=L.latLngBounds(pts);map.fitBounds(bounds,{padding:[30,30]});
document.getElementById('recenter').addEventListener('click',function(){followMe=true;if(here)map.panTo(here.getLatLng(),{animate:true});});
map.on('dragstart',function(){followMe=false;});
function updateGroundZero(data){
  if(data.current){if(!here){here=L.circleMarker([data.current.lat,data.current.lng],{radius:8,weight:3,color:'#3aa0ff'}).addTo(map).bindTooltip('You are here');}else here.setLatLng([data.current.lat,data.current.lng]);}
  if(data.route&&data.route.geometry&&data.route.geometry.length){var ll=data.route.geometry.map(function(c){return [c[1],c[0]]});if(routeLine)routeLine.remove();routeLine=L.polyline(ll,{weight:5,opacity:.9}).addTo(map);if(data.current&&followMe)map.panTo([data.current.lat,data.current.lng],{animate:true,duration:.25});}
}
window.updateGroundZero=updateGroundZero;window.addEventListener('message',function(e){if(e.data&&e.data.type==='groundzero-update')updateGroundZero(e.data)});
</script></body></html>`;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.deepTide },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.deepTide, padding: spacing.xl },
  msg: { ...typography.body, color: colors.textSecondary, textAlign: "center", marginTop: spacing.sm },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg, paddingTop: spacing.xl, paddingBottom: spacing.md },
  heading: { ...typography.subheading, color: colors.textPrimary },
  subheading: { ...typography.caption, color: colors.textFaint, marginTop: 2 },
  backText: { ...typography.bodyMedium, color: colors.brass },
  statusCard: { marginHorizontal: spacing.lg, marginBottom: spacing.sm, padding: spacing.md, borderRadius: radii.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceRaised, flexDirection: "row", alignItems: "center" },
  pin: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", marginRight: spacing.sm },
  pinText: { color: colors.laterite, fontSize: 24 },
  youAreHere: { ...typography.label, color: colors.brass },
  nextName: { ...typography.bodyMedium, color: colors.textPrimary, marginTop: 2 },
  routeMeta: { ...typography.caption, color: colors.textSecondary, marginTop: 2 },
  instruction: { ...typography.caption, color: colors.textPrimary, marginTop: spacing.xs },
  warning: { ...typography.caption, color: colors.brass, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  map: { flex: 1 },
  mapActions: { position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.lg, alignItems: "center" },
  navigateButton: { minWidth: 180, backgroundColor: colors.leaf, borderRadius: radii.pill, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, alignItems: "center", borderWidth: 1, borderColor: colors.border, elevation: 5 },
  navigateButtonText: { ...typography.bodyMedium, color: colors.textOnSand },
  backBtn: { marginTop: spacing.lg },
});
