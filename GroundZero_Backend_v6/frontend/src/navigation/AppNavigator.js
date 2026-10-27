import React, { useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { NavigationContainer, createNavigationContainerRef } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import StartScreen from "../screens/survey/StartScreen";
import SurveyScreen from "../screens/survey/SurveyScreen";
import GroupShareScreen from "../screens/survey/GroupShareScreen";
import HiveResultsScreen from "../screens/hive/HiveResultsScreen";
import CompanionScreen from "../screens/companion/CompanionScreen";
import ItineraryMapScreen from "../screens/map/ItineraryMapScreen";
import { PageHistory } from "./pageHistory";
import { colors, radii, spacing, typography } from "../theme/tokens";

const Stack = createNativeStackNavigator();
const navigationRef = createNavigationContainerRef();

export default function AppNavigator() {
  const [profileId, setProfileId] = useState(null);
  const [groupSessionId, setGroupSessionId] = useState(null);
  const [joinCode, setJoinCode] = useState(undefined);
  const [tripItinerary, setTripItinerary] = useState(null);
  const historyRef = useRef(new PageHistory());
  const [historyState, setHistoryState] = useState({ back: false, forward: false });
  const replayingRef = useRef(false);

  function recordState(state) {
    const route = state?.routes?.[state.index ?? 0];
    if (!route) return;
    if (!historyRef.current.current) historyRef.current.reset(route.name, route.params);
    else if (!replayingRef.current) historyRef.current.visit(route.name, route.params);
    replayingRef.current = false;
    setHistoryState({ back: !!historyRef.current.current?.prev, forward: !!historyRef.current.current?.next });
  }

  function goBackLinked() {
    const node = historyRef.current.back();
    if (!node || !navigationRef.isReady()) return;
    replayingRef.current = true;
    navigationRef.navigate(node.name, node.params);
    setHistoryState({ back: !!node.prev, forward: !!node.next });
  }

  function goForwardLinked() {
    const node = historyRef.current.forward();
    if (!node || !navigationRef.isReady()) return;
    replayingRef.current = true;
    navigationRef.navigate(node.name, node.params);
    setHistoryState({ back: !!node.prev, forward: !!node.next });
  }

  return (
    <View style={{ flex: 1 }}>
    <NavigationContainer ref={navigationRef} onStateChange={recordState}>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Start">
          {({ navigation }) => (
            <StartScreen
              onStartNew={() => {
                setJoinCode(undefined);
                navigation.navigate("Survey");
              }}
              onJoinGroup={(code) => {
                setJoinCode(code);
                navigation.navigate("Survey");
              }}
            />
          )}
        </Stack.Screen>

        <Stack.Screen name="Survey">
          {({ navigation }) => (
            <SurveyScreen
              joinGroupSessionId={joinCode}
              onComplete={(profile) => {
                setProfileId(profile.id);
                if (profile.group_session_id && !joinCode) {
                  // Only the group's first member (who minted the code) sees
                  // the share screen — someone who joined via a code already
                  // has it.
                  setGroupSessionId(profile.group_session_id);
                  navigation.navigate("GroupShare");
                } else {
                  navigation.navigate("HiveResults");
                }
              }}
            />
          )}
        </Stack.Screen>

        <Stack.Screen name="GroupShare">
          {({ navigation }) => (
            <GroupShareScreen
              groupSessionId={groupSessionId}
              onContinue={() => navigation.navigate("HiveResults")}
            />
          )}
        </Stack.Screen>

        <Stack.Screen name="HiveResults">
          {({ navigation }) => (
            <HiveResultsScreen
              profileId={profileId}
              onBeginTrip={({ itinerary }) => {
                setTripItinerary(itinerary);
                navigation.navigate("Companion");
              }}
            />
          )}
        </Stack.Screen>

        <Stack.Screen name="Companion">
          {({ navigation }) => (
            <CompanionScreen
              profileId={profileId}
              itinerary={tripItinerary}
              onOpenMap={(queue) => navigation.navigate("ItineraryMap", { queue })}
              onTripEnd={() => navigation.navigate("Start")}
            />
          )}
        </Stack.Screen>

        <Stack.Screen name="ItineraryMap">
          {({ navigation, route }) => (
            <ItineraryMapScreen
              itinerary={tripItinerary}
              queue={route.params?.queue || []}
              onClose={() => navigation.goBack()}
            />
          )}
        </Stack.Screen>
      </Stack.Navigator>
    </NavigationContainer>
    <View pointerEvents="box-none" style={styles.historyOverlay}>
      <Pressable disabled={!historyState.back} onPress={goBackLinked} style={[styles.historyButton, !historyState.back && styles.historyDisabled]}><Text style={styles.historyText}>←</Text></Pressable>
      <Pressable disabled={!historyState.forward} onPress={goForwardLinked} style={[styles.historyButton, !historyState.forward && styles.historyDisabled]}><Text style={styles.historyText}>→</Text></Pressable>
    </View>
    </View>
  );
}

const styles = StyleSheet.create({
  historyOverlay: { position: "absolute", right: spacing.md, bottom: spacing.lg, flexDirection: "row", gap: spacing.xs },
  historyButton: { width: 42, height: 42, borderRadius: radii.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceRaised, borderWidth: 1, borderColor: colors.border },
  historyDisabled: { opacity: 0.35 },
  historyText: { ...typography.subheading, color: colors.textPrimary },
});
