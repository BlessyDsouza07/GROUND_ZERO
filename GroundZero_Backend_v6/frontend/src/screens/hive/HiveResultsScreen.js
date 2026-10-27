import React, { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown } from "react-native-reanimated";
import { HiveApi, ItineraryApi, PlacesApi } from "../../api/client";
import * as Location from "expo-location";
import GlassCard from "../../components/GlassCard";
import Skeleton from "../../components/Skeleton";
import SignalRing from "../../components/SignalRing";
import { colors, radii, spacing, typography } from "../../theme/tokens";

const ROLE_LABELS = {
  grounding: "Easing you in",
  signature: "The one not to miss",
  anchor: "A proper break",
  personal: "Made for you",
  local_secret: "A local secret",
  tourist_pick: "Your addition",
};

const TRAVEL_LABELS = { walk: "Walk", auto: "Auto", cab: "Cab" };

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

// Backbone roles the tourist can rate/keep but not drag out of the day —
// mirrors HiveEngine's own _BUDGET_PROTECTED_ROLES reasoning: Grounding,
// Signature, Anchor and Local Secret are structural, not swappable on a
// whim from this screen. Personal, Wildcard and anything the tourist adds
// themselves are freely reorderable/removable.
const LOCKED_ROLES = new Set(["grounding", "signature", "anchor", "local_secret"]);

export default function HiveResultsScreen({ profileId, onBeginTrip }) {
  const [queue, setQueue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [items, setItems] = useState([]); // editable working copy
  const [removedIds, setRemovedIds] = useState([]);
  const [addedIds, setAddedIds] = useState([]);
  const [ratings, setRatings] = useState({}); // place_id -> "up" | "down"
  const [overallRating, setOverallRating] = useState(null);

  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState([]);
  const [saving, setSaving] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmError, setConfirmError] = useState(null);
  const [dbEmpty, setDbEmpty] = useState(false); // true => Layer 0's places table itself has 0 rows (data not imported yet), not a filtering problem

  useEffect(() => {
    if (!profileId) return;
    // Real geofence per blueprint 5.1: HIVE only considers places within a
    // reachable radius of where the tourist actually is (see
    // layer2/application/reachability.py). Location is optional and this
    // degrades to the previous full-dataset behavior if permission is
    // denied or unavailable — never blocks the trip over it. It also can
    // never zero out the queue by itself even with a wildly wrong location
    // (e.g. a simulator's default GPS fix) — reachability.py falls back to
    // the full candidate pool rather than returning nothing.
    (async () => {
      let lat, lon;
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status === "granted") {
          const pos = await Location.getCurrentPositionAsync({});
          lat = pos.coords.latitude;
          lon = pos.coords.longitude;
        }
      } catch {
        // no location — HiveApi.getRecommendations below just omits it
      }
      HiveApi.getRecommendations(profileId, undefined, lat, lon)
        .then((q) => {
          setQueue(q);
          setItems(q.items.map((i) => ({ place_id: i.place_id, place_name: i.place_name, role: i.role, _display: i })));
          if (q.items.length === 0) {
            // Distinguish "nothing was in the database to begin with" (an
            // admin needs to run import_master_data.py) from "places exist
            // but this profile's budget/timing genuinely ruled them all
            // out" — same empty queue, two very different fixes.
            PlacesApi.list()
              .then((places) => setDbEmpty(!places || places.length === 0))
              .catch(() => {});
          }
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    })();
  }, [profileId]);

  // Debounced auto-save of the draft on every edit — cheap, and means the
  // tourist never loses their reordering if they back out before hitting
  // Confirm. Doesn't touch feedback counters (save_draft never does — see
  // feedback_service.py docstring), so fiddling around costs nothing.
  useEffect(() => {
    if (!profileId || items.length === 0 || confirmed) return;
    const timer = setTimeout(() => {
      setSaving(true);
      ItineraryApi.save(profileId, {
        items: items.map((i) => ({ place_id: i.place_id, place_name: i.place_name, role: i.role })),
        removedPlaceIds: removedIds,
        addedPlaceIds: addedIds,
        placeRatings: ratings,
        overallRating,
      })
        .catch(() => {}) // best-effort — a failed draft save shouldn't interrupt the tourist
        .finally(() => setSaving(false));
    }, 600);
    return () => clearTimeout(timer);
  }, [items, removedIds, addedIds, ratings, overallRating]);

  const visibleItems = useMemo(() => items.filter((i) => !removedIds.includes(i.place_id)), [items, removedIds]);

  function moveItem(placeId, direction) {
    setItems((prev) => {
      const idx = prev.findIndex((i) => i.place_id === placeId);
      const swapIdx = idx + direction;
      if (idx < 0 || swapIdx < 0 || swapIdx >= prev.length) return prev;
      if (LOCKED_ROLES.has(prev[idx].role) || LOCKED_ROLES.has(prev[swapIdx].role)) return prev;
      const next = [...prev];
      [next[idx], next[swapIdx]] = [next[swapIdx], next[idx]];
      return next;
    });
  }

  function removeItem(placeId) {
    setRemovedIds((prev) => [...prev, placeId]);
  }

  function restoreItem(placeId) {
    setRemovedIds((prev) => prev.filter((id) => id !== placeId));
  }

  function rate(placeId, value) {
    setRatings((prev) => ({ ...prev, [placeId]: prev[placeId] === value ? undefined : value }));
  }

  async function runAddSearch(text) {
    setAddQuery(text);
    if (text.trim().length < 2) {
      setAddResults([]);
      return;
    }
    try {
      const all = await PlacesApi.list();
      const already = new Set(items.map((i) => i.place_id));
      setAddResults(
        all.filter((p) => p.name.toLowerCase().includes(text.toLowerCase()) && !already.has(p.id)).slice(0, 6)
      );
    } catch {
      setAddResults([]);
    }
  }

  function addPlace(place) {
    setItems((prev) => [...prev, { place_id: place.id, place_name: place.name, role: "tourist_pick" }]);
    setAddedIds((prev) => [...prev, place.id]);
    setAddQuery("");
    setAddResults([]);
  }

  async function confirmDay() {
    setSaving(true);
    setConfirmError(null);
    const payload = {
      items: items.map((i) => ({ place_id: i.place_id, place_name: i.place_name, role: i.role })),
      removedPlaceIds: removedIds,
      addedPlaceIds: addedIds,
      placeRatings: ratings,
      overallRating,
    };
    // Transient hiccups (a dev-server reload, a slow cold start) are common
    // enough to deserve two quick retries before ever bothering the tourist
    // with anything — most "Failed to fetch"s never make it past this.
    let lastErr = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await ItineraryApi.save(profileId, payload);
        await ItineraryApi.confirm(profileId);
        setConfirmed(true);
        setSaving(false);
        return;
      } catch (e) {
        lastErr = e;
        if (attempt < 2) await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
      }
    }
    // Everything Layer 3 needs (the itinerary itself) already lives in
    // `items`, client-side, so the tourist can still start their trip —
    // only the *saved copy on the server* didn't go through. Technical
    // detail goes to the console for developers; the tourist only ever
    // sees a plain, reassuring line — never a URL or "check the backend".
    console.warn("Itinerary save failed after retries:", lastErr);
    setConfirmError("Your day is ready to go — we just couldn't back it up online right now.");
    setSaving(false);
  }

  if (loading) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.container}>
        <View style={{ marginTop: spacing.xxxl, alignItems: "center", marginBottom: spacing.xl }}>
          <SignalRing size={90} active />
          <Text style={styles.loadingText}>Putting your day together…</Text>
        </View>
        <Skeleton height={90} style={{ marginBottom: spacing.md }} />
        <Skeleton height={90} style={{ marginBottom: spacing.md }} />
        <Skeleton height={90} />
      </LinearGradient>
    );
  }

  if (error) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}>
        <Text style={styles.errorText}>Couldn't build your day: {error}</Text>
      </LinearGradient>
    );
  }

  if (!queue || queue.items.length === 0) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}>
        <SignalRing size={100} />
        <Text style={styles.emptyHeading}>{dbEmpty ? "No places loaded yet" : "Nothing quite fit today"}</Text>
        <Text style={styles.emptyBody}>
          {dbEmpty
            ? "Ground Zero's places database is empty — an admin needs to run the data import (python import_master_data.py, see INTEGRATION_NOTES.md) before any trip can be built."
            : "Your budget or timing ruled out everything available right now. Try widening either one."}
        </Text>
      </LinearGradient>
    );
  }

  if (confirmed) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}>
        <SignalRing size={100} active />
        <Text style={styles.emptyHeading}>Your day is set</Text>
        <Text style={styles.emptyBody}>{visibleItems.length} stops, your way. Time to go.</Text>
        {onBeginTrip && (
          <Pressable
            onPress={() =>
              onBeginTrip({
                profileId,
                itinerary: visibleItems.map((i) => i._display || { place_id: i.place_id, place_name: i.place_name, role: i.role }),
              })
            }
            style={styles.beginButton}
          >
            <Text style={styles.beginButtonText}>Begin your trip →</Text>
          </Pressable>
        )}
      </LinearGradient>
    );
  }

  return (
    <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>YOUR DAY</Text>
        <Text style={styles.heading}>{visibleItems.length} stops</Text>
        <Text style={styles.subheading}>
          Estimated total · ₹{queue.total_estimated_cost}
          {queue.slots_requested != null && queue.slots_filled != null && queue.slots_filled < queue.slots_requested
            ? ` · ${queue.slots_filled}/${queue.slots_requested} slots filled`
            : ""}
        </Text>
        <Text style={styles.editHint}>Reorder, remove, or add stops below — then confirm when you're happy.</Text>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
        {visibleItems.map((item, index) => {
          const display = item._display;
          const locked = LOCKED_ROLES.has(item.role);
          return (
            <Animated.View
              key={`${item.place_id}-${index}`}
              entering={FadeInDown.delay(index * 60).duration(350)}
              style={styles.row}
            >
              <View style={styles.threadColumn}>
                <View style={styles.threadDot} />
                {index < visibleItems.length - 1 && <View style={styles.threadLine} />}
              </View>

              <GlassCard style={styles.card}>
                <View style={styles.cardTopRow}>
                  <Text style={styles.roleTag}>{ROLE_LABELS[item.role] || item.role}</Text>
                  {display && <Text style={styles.time}>{formatTime(display.scheduled_time)}</Text>}
                </View>
                <Text style={styles.placeName}>{item.place_name}</Text>
                {display && <Text style={styles.reason}>{display.reason_selected}</Text>}
                {display && (
                  <View style={styles.metaRow}>
                    <Text style={styles.metaText}>
                      {index > 0 ? `${TRAVEL_LABELS[display.travel_mode] || display.travel_mode} · ${display.travel_time_minutes} min · ` : ""}
                      ₹{display.estimated_cost}
                    </Text>
                    {display.weather_adjusted && <Text style={styles.weatherNote}>· moved for weather</Text>}
                  </View>
                )}

                <View style={styles.actionRow}>
                  <View style={styles.reorderGroup}>
                    <Pressable
                      onPress={() => moveItem(item.place_id, -1)}
                      disabled={locked || index === 0}
                      style={[styles.iconButton, (locked || index === 0) && styles.iconButtonDisabled]}
                    >
                      <Text style={styles.iconButtonText}>↑</Text>
                    </Pressable>
                    <Pressable
                      onPress={() => moveItem(item.place_id, 1)}
                      disabled={locked || index === visibleItems.length - 1}
                      style={[styles.iconButton, (locked || index === visibleItems.length - 1) && styles.iconButtonDisabled]}
                    >
                      <Text style={styles.iconButtonText}>↓</Text>
                    </Pressable>
                  </View>

                  <View style={styles.rateGroup}>
                    <Pressable onPress={() => rate(item.place_id, "up")} style={styles.iconButton}>
                      <Text style={[styles.iconButtonText, ratings[item.place_id] === "up" && styles.rateActiveUp]}>👍</Text>
                    </Pressable>
                    <Pressable onPress={() => rate(item.place_id, "down")} style={styles.iconButton}>
                      <Text style={[styles.iconButtonText, ratings[item.place_id] === "down" && styles.rateActiveDown]}>👎</Text>
                    </Pressable>
                  </View>

                  {!locked && (
                    <Pressable onPress={() => removeItem(item.place_id)} style={styles.removeButton}>
                      <Text style={styles.removeButtonText}>Remove</Text>
                    </Pressable>
                  )}
                </View>
              </GlassCard>
            </Animated.View>
          );
        })}

        {removedIds.length > 0 && (
          <View style={styles.removedSection}>
            <Text style={styles.removedHeading}>Removed</Text>
            {removedIds.map((id) => {
              const item = items.find((i) => i.place_id === id);
              if (!item) return null;
              return (
                <View key={id} style={styles.removedRow}>
                  <Text style={styles.removedName}>{item.place_name}</Text>
                  <Pressable onPress={() => restoreItem(id)}>
                    <Text style={styles.restoreText}>Undo</Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        )}

        <View style={styles.addSection}>
          <Text style={styles.addHeading}>Add a place of your own</Text>
          <TextInput
            style={styles.addInput}
            placeholder="Search by name…"
            placeholderTextColor={colors.textFaint}
            value={addQuery}
            onChangeText={runAddSearch}
          />
          {addResults.map((p) => (
            <Pressable key={p.id} onPress={() => addPlace(p)} style={styles.addResultRow}>
              <Text style={styles.addResultName}>{p.name}</Text>
              <Text style={styles.addResultAdd}>+ Add</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.overallSection}>
          <Text style={styles.addHeading}>How does this day look overall?</Text>
          <View style={styles.starsRow}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} onPress={() => setOverallRating(n)}>
                <Text style={[styles.star, overallRating != null && n <= overallRating && styles.starActive]}>★</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {confirmError && (
          <View style={styles.confirmErrorBox}>
            <Text style={styles.errorText}>{confirmError}</Text>
            <Text style={styles.confirmErrorHint}>
              Your day itself is fine — it's saved on this device either way. We'll keep it backed up next time
              you're online.
            </Text>
            <Pressable onPress={() => setConfirmed(true)} style={styles.continueAnywayButton}>
              <Text style={styles.continueAnywayText}>Continue without saving →</Text>
            </Pressable>
          </View>
        )}

        <Pressable
          onPress={confirmDay}
          disabled={saving || visibleItems.length === 0}
          style={[styles.confirmButton, (saving || visibleItems.length === 0) && styles.confirmButtonDisabled]}
        >
          <Text style={styles.confirmButtonText}>{saving ? "Saving…" : "Confirm my day"}</Text>
        </Pressable>
      </ScrollView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: spacing.lg, paddingTop: spacing.xxl },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  loadingText: { ...typography.body, color: colors.textSecondary, marginTop: spacing.md },
  errorText: { ...typography.body, color: colors.laterite, textAlign: "center", marginBottom: spacing.md },
  confirmErrorBox: { marginBottom: spacing.md, alignItems: "center" },
  confirmErrorHint: { ...typography.caption, color: colors.textFaint, textAlign: "center", marginBottom: spacing.sm },
  continueAnywayButton: { paddingVertical: spacing.xs },
  continueAnywayText: { ...typography.bodyMedium, color: colors.brass, textAlign: "center" },
  emptyHeading: { ...typography.heading, color: colors.textPrimary, marginTop: spacing.lg, textAlign: "center" },
  emptyBody: { ...typography.body, color: colors.textSecondary, textAlign: "center", marginTop: spacing.sm, maxWidth: 280 },

  header: { marginBottom: spacing.lg },
  eyebrow: { ...typography.label, color: colors.brassDim, marginBottom: spacing.xs },
  heading: { ...typography.heading, color: colors.textPrimary },
  subheading: { ...typography.body, color: colors.textSecondary, marginTop: 2 },
  editHint: { ...typography.caption, color: colors.textFaint, marginTop: spacing.xs },

  row: { flexDirection: "row" },
  threadColumn: { width: 24, alignItems: "center" },
  threadDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.brass, marginTop: 22 },
  threadLine: { width: 1, flex: 1, backgroundColor: colors.border, marginTop: 4, marginBottom: 4 },

  card: { flex: 1, marginLeft: spacing.sm, marginBottom: spacing.lg },
  cardTopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  roleTag: { ...typography.label, color: colors.leaf, textTransform: "uppercase" },
  time: { ...typography.caption, color: colors.textFaint },
  placeName: { ...typography.subheading, color: colors.textPrimary, marginTop: spacing.xs, fontSize: 19 },
  reason: { ...typography.body, color: colors.textSecondary, marginTop: spacing.xs },
  metaRow: { flexDirection: "row", marginTop: spacing.sm },
  metaText: { ...typography.caption, color: colors.textFaint },
  weatherNote: { ...typography.caption, color: colors.brassDim, marginLeft: 4 },

  actionRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.sm, gap: spacing.sm },
  reorderGroup: { flexDirection: "row", gap: spacing.xs },
  rateGroup: { flexDirection: "row", gap: spacing.xs },
  iconButton: {
    width: 32, height: 32, borderRadius: radii?.sm || 8, backgroundColor: colors.surfaceRaised,
    alignItems: "center", justifyContent: "center",
  },
  iconButtonDisabled: { opacity: 0.3 },
  iconButtonText: { fontSize: 14, color: colors.textPrimary },
  rateActiveUp: { color: colors.leaf },
  rateActiveDown: { color: colors.laterite },
  removeButton: { marginLeft: "auto" },
  removeButtonText: { ...typography.caption, color: colors.laterite },

  removedSection: { marginTop: spacing.sm, marginBottom: spacing.lg, paddingHorizontal: spacing.sm },
  removedHeading: { ...typography.label, color: colors.textFaint, marginBottom: spacing.xs },
  removedRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.xs },
  removedName: { ...typography.body, color: colors.textFaint, textDecorationLine: "line-through" },
  restoreText: { ...typography.caption, color: colors.brass },

  addSection: { marginBottom: spacing.lg, paddingHorizontal: spacing.sm },
  addHeading: { ...typography.label, color: colors.textSecondary, marginBottom: spacing.sm },
  addInput: {
    ...typography.body, color: colors.textPrimary, backgroundColor: colors.surface,
    borderRadius: radii?.sm || 8, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderWidth: 1, borderColor: colors.border,
  },
  addResultRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  addResultName: { ...typography.body, color: colors.textPrimary },
  addResultAdd: { ...typography.caption, color: colors.brass },

  overallSection: { marginBottom: spacing.xl, paddingHorizontal: spacing.sm },
  starsRow: { flexDirection: "row", gap: spacing.sm },
  star: { fontSize: 28, color: colors.textFaint },
  starActive: { color: colors.brass },

  confirmButton: {
    backgroundColor: colors.leaf, borderRadius: radii?.md || 12, paddingVertical: spacing.md,
    alignItems: "center", marginTop: spacing.sm,
  },
  confirmButtonDisabled: { opacity: 0.5 },
  confirmButtonText: { ...typography.subheading, color: colors.textOnSand },

  beginButton: {
    backgroundColor: colors.leaf, borderRadius: radii?.md || 12, paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl, alignItems: "center", marginTop: spacing.xl,
  },
  beginButtonText: { ...typography.subheading, color: colors.textOnSand },
});
