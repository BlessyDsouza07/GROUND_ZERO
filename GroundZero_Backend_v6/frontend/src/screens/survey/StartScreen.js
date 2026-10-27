import React, { useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeIn, FadeInDown, FadeOut } from "react-native-reanimated";
import SignalRing from "../../components/SignalRing";
import { colors, radii, spacing, typography } from "../../theme/tokens";

export default function StartScreen({ onStartNew, onJoinGroup }) {
  const [joinMode, setJoinMode] = useState(false);
  const [code, setCode] = useState("");

  return (
    <LinearGradient
      colors={[colors.deepTideDeeper, colors.deepTide, colors.surface]}
      locations={[0, 0.55, 1]}
      style={styles.container}
    >
      {/* A faint laterite glow low in the frame — the only warm light in an
          otherwise cool, quiet composition, like dusk light off a tiled roof. */}
      <View style={styles.glow} pointerEvents="none" />

      <View style={styles.ringWrap}>
        <SignalRing size={172} />
      </View>

      <Animated.View entering={FadeInDown.delay(200).duration(700)} style={styles.textBlock}>
        <Text style={styles.eyebrow}>MANGALURU</Text>
        <Text style={styles.hero}>Ground Zero</Text>
        <Text style={styles.tagline}>
          A quiet local guide. It listens first, and only speaks when it has something worth
          saying.
        </Text>
      </Animated.View>

      <Animated.View entering={FadeIn.delay(500).duration(500)} style={styles.actions}>
        {!joinMode ? (
          <>
            <TouchableOpacity style={styles.primaryButton} onPress={onStartNew} activeOpacity={0.85}>
              <Text style={styles.primaryButtonText}>Begin</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.textButton} onPress={() => setJoinMode(true)}>
              <Text style={styles.textButtonText}>I have a group code</Text>
            </TouchableOpacity>
          </>
        ) : (
          <Animated.View entering={FadeIn.duration(300)} exiting={FadeOut.duration(200)}>
            <TextInput
              style={styles.input}
              value={code}
              onChangeText={setCode}
              placeholder="Enter your group's code"
              placeholderTextColor={colors.textFaint}
              autoCapitalize="none"
            />
            <TouchableOpacity
              style={[styles.primaryButton, !code.trim() && styles.primaryButtonDisabled]}
              disabled={!code.trim()}
              onPress={() => onJoinGroup(code.trim())}
              activeOpacity={0.85}
            >
              <Text style={styles.primaryButtonText}>Join group</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.textButton} onPress={() => setJoinMode(false)}>
              <Text style={styles.textButtonText}>Back</Text>
            </TouchableOpacity>
          </Animated.View>
        )}
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  glow: {
    position: "absolute",
    bottom: -120,
    width: 420,
    height: 420,
    borderRadius: 210,
    backgroundColor: colors.laterite,
    opacity: 0.1,
  },
  ringWrap: { marginBottom: spacing.xl },
  textBlock: { alignItems: "center", marginBottom: spacing.xxl },
  eyebrow: {
    ...typography.label,
    color: colors.brassDim,
    marginBottom: spacing.sm,
  },
  hero: {
    ...typography.hero,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  tagline: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: "center",
    maxWidth: 280,
  },
  actions: { width: "100%", maxWidth: 340 },
  primaryButton: {
    backgroundColor: colors.laterite,
    borderRadius: radii.pill,
    paddingVertical: 16,
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  primaryButtonDisabled: { opacity: 0.35 },
  primaryButtonText: { ...typography.subheading, color: colors.sand },
  textButton: { paddingVertical: spacing.sm, alignItems: "center" },
  textButtonText: { ...typography.body, color: colors.textSecondary },
  input: {
    backgroundColor: "rgba(241,230,210,0.06)",
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    color: colors.textPrimary,
    ...typography.body,
    marginBottom: spacing.md,
  },
});
