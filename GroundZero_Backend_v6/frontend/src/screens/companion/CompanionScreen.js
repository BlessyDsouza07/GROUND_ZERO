import React, { useEffect, useRef, useState } from "react";
import { Alert, Linking, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown, FadeIn } from "react-native-reanimated";
import * as Location from "expo-location";
import * as Speech from "expo-speech";
import * as Notifications from "expo-notifications";
import { Layer3Api, EventsApi } from "../../api/client_layer3";
import GlassCard from "../../components/GlassCard";
import SignalRing from "../../components/SignalRing";
import { configureNotifications, notifyPlace, READ_ALOUD_ACTION } from "../../services/notifications";
import { colors, radii, spacing, typography } from "../../theme/tokens";

const VOICE_TUNING = {
  warm: { rate: 0.98, pitch: 1.0 },
  historian: { rate: 0.85, pitch: 0.82 },
  witty: { rate: 1.1, pitch: 1.18 },
};
const EVALUATE_INTERVAL_MS = 45_000;
const SOS_NUMBER = "112";

export default function CompanionScreen({ profileId, itinerary, onOpenMap, onTripEnd }) {
  const [sessionId, setSessionId] = useState(null);
  const [queue, setQueue] = useState([]);
  const [startError, setStartError] = useState(null);
  const [starting, setStarting] = useState(true);
  const [status, setStatus] = useState("active");
  const [decision, setDecision] = useState(null);
  const [checking, setChecking] = useState(false);
  const [tellMore, setTellMore] = useState(null);
  const [tellMoreLoading, setTellMoreLoading] = useState(false);
  const [arrivedPlace, setArrivedPlace] = useState(null);
  const [tripOptionsOpen, setTripOptionsOpen] = useState(false);
  const [sosOpen, setSosOpen] = useState(false);
  const [quietUntil, setQuietUntil] = useState(null);
  const [events, setEvents] = useState([]);
  const [voice, setVoice] = useState("warm");
  const [muted, setMuted] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);

  const locationRef = useRef({ lat: undefined, lng: undefined });
  const sessionIdRef = useRef(null);
  const voiceRef = useRef("warm");
  const mutedRef = useRef(false);

  useEffect(() => {
    voiceRef.current = voice;
  }, [voice]);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    if (!profileId || !itinerary || itinerary.length === 0) {
      setStarting(false);
      return;
    }
    (async () => {
      const notifications = await configureNotifications();
      setNotificationsEnabled(notifications);
      try {
        const session = await Layer3Api.startSession(profileId, itinerary);
        setSessionId(session.session_id);
        sessionIdRef.current = session.session_id;
        setQueue(session.queue || []);
        setVoice(session.voice || "warm");
        setStatus(session.status || "active");
      } catch (e) {
        setStartError(e.message);
      } finally {
        setStarting(false);
      }
    })();
  }, [profileId, itinerary]);

  useEffect(() => {
    if (!sessionId) return undefined;
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      if (response.actionIdentifier !== READ_ALOUD_ACTION) return;
      const text = response.notification.request.content.data?.voiceText;
      if (!text || mutedRef.current) return;
      const tuning = VOICE_TUNING[voiceRef.current] || VOICE_TUNING.warm;
      Speech.stop();
      Speech.speak(String(text), { rate: tuning.rate, pitch: tuning.pitch });
    });
    return () => sub.remove();
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || status !== "active") return undefined;
    let cancelled = false;

    async function refreshLocation() {
      try {
        const { status: permission } = await Location.requestForegroundPermissionsAsync();
        if (permission !== "granted") return;
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        if (!cancelled) locationRef.current = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      } catch {
        // Location is an enhancement; the trip stays usable without it.
      }
    }

    async function checkIn() {
      await refreshLocation();
      const { lat, lng } = locationRef.current;
      setChecking(true);
      try {
        if (lat !== undefined && lng !== undefined) {
          await Layer3Api.ping(sessionIdRef.current, lat, lng);
        }
        const d = await Layer3Api.evaluate(sessionIdRef.current, lat, lng);
        if (!cancelled) applyDecision(d);
      } catch {
        // A transient context failure must not stop the trip.
      } finally {
        if (!cancelled) setChecking(false);
      }
    }

    checkIn();
    const id = setInterval(checkIn, EVALUATE_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sessionId, status]);

  useEffect(() => {
    EventsApi.itinerarySafe().then(setEvents).catch(() => setEvents([]));
  }, []);

  function speak(text) {
    if (!text || mutedRef.current) return;
    const tuning = VOICE_TUNING[voiceRef.current] || VOICE_TUNING.warm;
    Speech.stop();
    Speech.speak(text, { rate: tuning.rate, pitch: tuning.pitch });
  }

  async function applyDecision(d) {
    setDecision(d);
    setTellMore(null);
    if (d.decision === "speak" && d.message?.notification_id) {
      Layer3Api.engageNotification(sessionIdRef.current, d.message.notification_id).catch(() => {});
      const voiceText = [d.message.text, d.message.etiquette_whisper].filter(Boolean).join(" ");
      speak(voiceText);
      if (notificationsEnabled) {
        notifyPlace({
          title: d.message.place_name || "Ground Zero",
          body: d.message.text,
          voiceText,
          placeId: d.message.place_id,
        });
      }
    } else if (d.decision === "safety_alert") {
      speak(d.message?.text || "Please take care right now.");
    }
  }

  async function imHere() {
    const { lat, lng } = locationRef.current;
    setChecking(true);
    try {
      const d = await Layer3Api.evaluate(sessionIdRef.current, lat, lng, { manualTrigger: true });
      applyDecision(d);
    } catch (e) {
      Alert.alert("Couldn't check in", e.message);
    } finally {
      setChecking(false);
    }
  }

  async function handleTellMore(placeId = arrivedPlace?.place_id) {
    if (!placeId || tellMoreLoading) return;
    setTellMoreLoading(true);
    try {
      const res = await Layer3Api.tellMore(sessionIdRef.current, {
        placeId,
      });
      const text = res.available === false
        ? "Information is not available for this place at the moment."
        : (res.text || res.answer || "Information is not available for this place at the moment.");
      setTellMore(text);
      speak(text);
    } catch {
      setTellMore("Information is not available for this place at the moment.");
      speak("Information is not available for this place at the moment.");
    } finally {
      setTellMoreLoading(false);
    }
  }

  async function changeTripState(nextStatus) {
    try {
      const result = await Layer3Api.updateState(sessionIdRef.current, { status: nextStatus });
      setStatus(result.status || nextStatus);
      return true;
    } catch (e) {
      Alert.alert("Trip state couldn't be changed", e.message);
      return false;
    }
  }

  function pauseTrip() { setTripOptionsOpen(true); }

  async function resumeTrip() {
    try { await Layer3Api.clearSos(sessionIdRef.current); } catch {}
    await changeTripState("active");
  }

  async function exitTrip() {
    const ok = await changeTripState("ended_early");
    if (ok) onTripEnd?.("ended_early");
  }

  async function confirmSos() {
    setSosOpen(false);
    try {
      const { lat, lng } = locationRef.current;
      try { await Layer3Api.sos(sessionIdRef.current, lat, lng); } catch {}
      await changeTripState("paused");
      const telUrl = `tel:${SOS_NUMBER}`;
      if (Platform.OS === "web") {
        if (typeof window !== "undefined") window.location.href = telUrl;
        return;
      }
      const supported = await Linking.canOpenURL(telUrl);
      if (supported) await Linking.openURL(telUrl);
      else Alert.alert("Phone app unavailable", `This device cannot open a phone app. Please call ${SOS_NUMBER} manually.`);
    } catch (e) {
      Alert.alert("SOS phone access unavailable", "The trip is paused. Please open your device phone app and call 112.");
    }
  }

  function startSosFlow() { setSosOpen(true); }

  async function markArrived(placeId) {
    try {
      const result = await Layer3Api.recordVisit(sessionId, placeId);
      const place = queue.find((s) => s.place_id === placeId);
      setArrivedPlace({ place_id: placeId, place_name: place?.place_name || placeId });
      setTellMore(null);
      const session = await Layer3Api.getSession(sessionId);
      const nextQueue = session.queue || [];
      setQueue(nextQueue);
      if (!nextQueue.some((s) => !["visited", "skipped", "dropped", "replaced"].includes(s.status))) {
        const completed = await changeTripState("completed");
        if (completed) onTripEnd?.("completed");
      }
      return result;
    } catch (e) {
      Alert.alert("Couldn't record your visit", e.message);
    }
  }

  if (starting) {
    return <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}><SignalRing size={100} /><Text style={styles.loadingText}>Waking up your companion…</Text></LinearGradient>;
  }
  if (!itinerary || itinerary.length === 0) {
    return <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}><Text style={styles.emptyHeading}>No trip to accompany yet</Text><Text style={styles.emptyBody}>Confirm a day from your HIVE results first, then come back here.</Text></LinearGradient>;
  }
  if (startError) {
    return <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}><Text style={styles.emptyHeading}>Couldn't start your companion</Text><Text style={styles.emptyBody}>{startError}</Text></LinearGradient>;
  }

  const isSafety = decision?.decision === "safety_alert";
  const remaining = queue.filter((s) => !["visited", "skipped", "dropped", "replaced"].includes(s.status));
  const paused = status === "paused";

  return (
    <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.gradient}>
      <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.eyebrow}>YOUR TRIP</Text>
            <Text style={styles.heading}>{paused ? "Trip paused" : "Companion"}</Text>
            <Text style={styles.subheading}>{paused ? "Your place in the day is saved." : "Quietly watching — it'll speak up only when it's worth it."}</Text>
            <Text style={styles.locationNote}>{notificationsEnabled ? "Notifications are enabled; each place notification includes Read aloud." : "Notifications are off; the trip still works in the app."}</Text>
          </View>
          <Pressable onPress={() => setTripOptionsOpen(true)} style={styles.optionsButton}><Text style={styles.optionsButtonText}>Trip options</Text></Pressable>
        </View>

        {paused ? (
          <GlassCard style={styles.pauseCard}>
            <Text style={styles.pauseHeading}>Trip on hold</Text>
            <Text style={styles.messageText}>No location polling or trip guidance runs while the trip is paused.</Text>
            <View style={styles.pauseActions}>
              <Pressable onPress={resumeTrip} style={styles.primaryButton}><Text style={styles.primaryButtonText}>Resume trip</Text></Pressable>
              <Pressable onPress={exitTrip} style={styles.secondaryButton}><Text style={styles.secondaryButtonText}>Exit trip</Text></Pressable>
            </View>
          </GlassCard>
        ) : (
          <>
            <View style={styles.ringSection}>
              <SignalRing size={140} active={checking || decision?.decision === "speak"} />
              <Pressable onPress={imHere} style={styles.imHereButton}><Text style={styles.imHereButtonText}>I'm here — check now</Text></Pressable>
            </View>

            {arrivedPlace && (
              <Animated.View entering={FadeInDown}>
                <GlassCard style={styles.tellMoreCard}>
                  <Text style={styles.messagePlace}>{arrivedPlace.place_name}</Text>
                  {!tellMore ? (
                    <Pressable onPress={() => handleTellMore(arrivedPlace.place_id)} style={styles.tellMoreButton}>
                      <Text style={styles.tellMoreButtonText}>{tellMoreLoading ? "Loading…" : "Tell me more"}</Text>
                    </Pressable>
                  ) : (
                    <View style={styles.tellMoreResultRow}>
                      <Text style={styles.tellMoreText}>{tellMore}</Text>
                      <Pressable onPress={() => speak(tellMore)} style={styles.inlineVoiceButton}><Text style={styles.tellMoreButtonText}>🔊</Text></Pressable>
                    </View>
                  )}
                </GlassCard>
              </Animated.View>
            )}

            {decision?.decision === "speak" && decision.message && (
              <Animated.View entering={FadeInDown}>
                <GlassCard style={isSafety ? styles.safetyCard : undefined}>
                  {decision.message.place_name && <Text style={styles.messagePlace}>{decision.message.place_name}</Text>}
                  <Text style={styles.messageText}>{decision.message.text}</Text>
                  {decision.message.etiquette_whisper && <Text style={styles.etiquette}>💡 {decision.message.etiquette_whisper}</Text>}
                </GlassCard>
              </Animated.View>
            )}

            {isSafety && <Animated.View entering={FadeInDown}><GlassCard style={styles.safetyCard}><Text style={styles.safetyHeading}>⚠ Safety alert</Text><Text style={styles.messageText}>{decision.message?.text || "Please take care right now."}</Text></GlassCard></Animated.View>}

            {remaining.length > 0 && (
              <View style={styles.stopsSection}>
                <Text style={styles.sectionLabel}>Still ahead today</Text>
                {remaining.map((slot) => (
                  <View key={slot.slot_id || slot.place_id} style={styles.stopRow}>
                    <Text style={styles.stopName}>{slot.place_name || slot.place_id}</Text>
                    <Pressable onPress={() => markArrived(slot.place_id)}><Text style={styles.arrivedText}>I've arrived</Text></Pressable>
                  </View>
                ))}
              </View>
            )}

            {events.length > 0 && <Animated.View entering={FadeIn} style={styles.eventsSection}><Text style={styles.sectionLabel}>Happening nearby, verified</Text>{events.slice(0, 4).map((ev) => <GlassCard key={ev.id} style={styles.eventCard}><Text style={styles.eventTitle}>{ev.title}</Text>{ev.venue && <Text style={styles.eventVenue}>{ev.venue}</Text>}</GlassCard>)}</Animated.View>}

            <View style={styles.controlsRow}>
              <Pressable onPress={() => onOpenMap?.(queue)} style={styles.quietButton}><Text style={styles.quietButtonText}>🗺️ Route map</Text></Pressable>
              <Pressable onPress={() => { setMuted((m) => !m); }} style={styles.quietButton}><Text style={styles.quietButtonText}>{muted ? "🔇 Voice off" : "🔊 Voice on"}</Text></Pressable>
              <Pressable onPress={async () => { try { if (quietUntil) { await Layer3Api.setQuietHours(sessionId, 0); setQuietUntil(null); } else { const res = await Layer3Api.setQuietHours(sessionId, 60); setQuietUntil(res.quiet_until); } } catch (e) { Alert.alert("Couldn't update Quiet Hours", e.message); } }} style={styles.quietButton}><Text style={styles.quietButtonText}>{quietUntil ? "🔕 Quiet hours on" : "🔕 Quiet for 1 hr"}</Text></Pressable>
            </View>

            <Pressable onPress={startSosFlow} style={styles.sosButton}><Text style={styles.sosButtonText}>SOS — I need help</Text></Pressable>
          </>
        )}
      </ScrollView>

      <Modal visible={tripOptionsOpen} transparent animationType="fade" onRequestClose={() => setTripOptionsOpen(false)}>
        <View style={styles.modalBackdrop}>
          <GlassCard style={styles.modalCard}>
            <View style={styles.modalHeader}><Text style={styles.modalTitle}>Trip options</Text><Pressable onPress={() => setTripOptionsOpen(false)}><Text style={styles.closeText}>Close ✕</Text></Pressable></View>
            <Text style={styles.modalBody}>Choose whether to pause this trip and resume later, or end it now.</Text>
            <Pressable onPress={async () => { setTripOptionsOpen(false); await changeTripState("paused"); }} style={styles.primaryButton}><Text style={styles.primaryButtonText}>Pause and resume later</Text></Pressable>
            <Pressable onPress={async () => { setTripOptionsOpen(false); await exitTrip(); }} style={styles.dangerButton}><Text style={styles.dangerButtonText}>Exit trip</Text></Pressable>
          </GlassCard>
        </View>
      </Modal>

      <Modal visible={sosOpen} transparent animationType="fade" onRequestClose={() => setSosOpen(false)}>
        <View style={styles.modalBackdrop}>
          <GlassCard style={styles.modalCard}>
            <View style={styles.modalHeader}><Text style={styles.modalTitle}>SOS — I need help</Text><Pressable onPress={() => setSosOpen(false)}><Text style={styles.closeText}>Close ✕</Text></Pressable></View>
            <Text style={styles.modalBody}>The trip will pause first. Ground Zero will then ask the device to open its phone app for emergency number 112.</Text>
            <Pressable onPress={confirmSos} style={styles.sosConfirmButton}><Text style={styles.sosButtonText}>Open phone app</Text></Pressable>
          </GlassCard>
        </View>
      </Modal>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  gradient: { flex: 1 },
  container: { paddingHorizontal: spacing.lg, paddingTop: spacing.xxl, paddingBottom: spacing.xxxl },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  loadingText: { ...typography.body, color: colors.textSecondary, marginTop: spacing.md },
  emptyHeading: { ...typography.heading, color: colors.textPrimary, textAlign: "center" },
  emptyBody: { ...typography.body, color: colors.textSecondary, textAlign: "center", marginTop: spacing.sm, maxWidth: 280 },
  header: { marginBottom: spacing.lg, flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  headerCopy: { flex: 1 },
  optionsButton: { backgroundColor: colors.surfaceRaised, borderRadius: radii.pill, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.border, marginLeft: spacing.sm },
  optionsButtonText: { ...typography.caption, color: colors.brass },
  eyebrow: { ...typography.label, color: colors.brassDim, marginBottom: spacing.xs },
  heading: { ...typography.heading, color: colors.textPrimary },
  subheading: { ...typography.body, color: colors.textSecondary, marginTop: 2 },
  locationNote: { ...typography.caption, color: colors.textFaint, marginTop: spacing.xs },
  ringSection: { alignItems: "center", marginBottom: spacing.lg },
  imHereButton: { marginTop: spacing.md, backgroundColor: colors.surfaceRaised, borderRadius: radii.pill, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border },
  imHereButtonText: { ...typography.bodyMedium, color: colors.textPrimary },
  safetyCard: { borderColor: colors.laterite, borderWidth: 1.5 },
  safetyHeading: { ...typography.subheading, color: colors.laterite, marginBottom: spacing.xs },
  messagePlace: { ...typography.subheading, color: colors.textPrimary, marginBottom: spacing.xs },
  messageText: { ...typography.body, color: colors.textPrimary },
  etiquette: { ...typography.caption, color: colors.brass, marginTop: spacing.sm },
  tellMoreCard: { marginTop: spacing.md, borderColor: colors.brass, borderWidth: 1 },
  tellMoreRow: { marginTop: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  tellMoreButton: { backgroundColor: colors.surfaceRaised, borderRadius: radii.pill, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, alignSelf: "flex-start", borderWidth: 1, borderColor: colors.border },
  tellMoreButtonText: { ...typography.bodyMedium, color: colors.brass },
  tellMoreResultRow: { marginTop: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  tellMoreText: { ...typography.body, color: colors.textSecondary, flex: 1 },
  inlineVoiceButton: { minWidth: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceRaised, borderWidth: 1, borderColor: colors.border },
  stopsSection: { marginTop: spacing.lg },
  sectionLabel: { ...typography.label, color: colors.textSecondary, marginBottom: spacing.sm },
  stopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  stopName: { ...typography.body, color: colors.textPrimary, flexShrink: 1, marginRight: spacing.sm },
  arrivedText: { ...typography.caption, color: colors.brass },
  eventsSection: { marginTop: spacing.lg },
  eventCard: { marginBottom: spacing.sm },
  eventTitle: { ...typography.bodyMedium, color: colors.textPrimary },
  eventVenue: { ...typography.caption, color: colors.textFaint, marginTop: 2 },
  controlsRow: { marginTop: spacing.xl, flexDirection: "row", flexWrap: "wrap", justifyContent: "center" },
  quietButton: { backgroundColor: colors.surfaceRaised, borderRadius: radii.pill, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, marginHorizontal: spacing.xs, marginBottom: spacing.sm },
  quietButtonText: { ...typography.caption, color: colors.textSecondary },
  sosButton: { backgroundColor: colors.laterite, borderRadius: radii.md, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.lg },
  sosButtonText: { ...typography.subheading, color: colors.sand },
  pauseCard: { borderColor: colors.brass, borderWidth: 1 },
  pauseHeading: { ...typography.heading, color: colors.textPrimary, marginBottom: spacing.sm },
  pauseActions: { marginTop: spacing.lg, flexDirection: "row", gap: spacing.sm },
  primaryButton: { flex: 1, backgroundColor: colors.leaf, borderRadius: radii.sm, paddingVertical: spacing.md, alignItems: "center" },
  primaryButtonText: { ...typography.bodyMedium, color: colors.textOnSand },
  secondaryButton: { flex: 1, backgroundColor: colors.surfaceRaised, borderRadius: radii.sm, paddingVertical: spacing.md, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  secondaryButtonText: { ...typography.bodyMedium, color: colors.textPrimary },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.65)", justifyContent: "center", alignItems: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 520, backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1 },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  modalTitle: { ...typography.heading, color: colors.textPrimary, flexShrink: 1 },
  closeText: { ...typography.caption, color: colors.brass },
  modalBody: { ...typography.body, color: colors.textSecondary, marginBottom: spacing.md },
  dangerButton: { marginTop: spacing.sm, backgroundColor: colors.surfaceRaised, borderRadius: radii.sm, paddingVertical: spacing.md, alignItems: "center", borderWidth: 1, borderColor: colors.laterite },
  dangerButtonText: { ...typography.bodyMedium, color: colors.laterite },
  sosConfirmButton: { backgroundColor: colors.laterite, borderRadius: radii.md, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.sm },
});
