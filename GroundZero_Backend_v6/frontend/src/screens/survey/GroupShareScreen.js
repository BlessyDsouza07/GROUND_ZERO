import React, { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown } from "react-native-reanimated";
import { SurveyApi } from "../../api/client";
import GlassCard from "../../components/GlassCard";
import { colors, radii, spacing, typography } from "../../theme/tokens";

export default function GroupShareScreen({ groupSessionId, onContinue }) {
  const [members, setMembers] = useState([]);

  useEffect(() => {
    if (!groupSessionId) return;
    const poll = () => SurveyApi.getGroupMembers(groupSessionId).then(setMembers).catch(() => {});
    poll();
    const interval = setInterval(poll, 4000);
    return () => clearInterval(interval);
  }, [groupSessionId]);

  return (
    <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.container}>
      <Animated.View entering={FadeInDown.duration(500)}>
        <Text style={styles.eyebrow}>YOUR GROUP</Text>
        <Text style={styles.heading}>Share this code</Text>

        <GlassCard style={styles.codeCard}>
          <Text style={styles.code}>{groupSessionId}</Text>
        </GlassCard>

        <Text style={styles.body}>
          Each person in your group completes their own quick survey, then joins with this code.
        </Text>

        <View style={styles.memberRow}>
          <View style={styles.memberDot} />
          <Text style={styles.memberText}>
            {members.length} {members.length === 1 ? "person has" : "people have"} joined so far
          </Text>
        </View>

        <TouchableOpacity style={styles.continueButton} onPress={onContinue} activeOpacity={0.85}>
          <Text style={styles.continueButtonText}>Continue to my day</Text>
        </TouchableOpacity>
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.lg, paddingTop: spacing.xxxl },
  eyebrow: { ...typography.label, color: colors.brassDim, marginBottom: spacing.sm },
  heading: { ...typography.heading, color: colors.textPrimary, marginBottom: spacing.xl },
  codeCard: { alignItems: "center", marginBottom: spacing.lg, borderColor: "rgba(201,162,83,0.4)" },
  code: {
    ...typography.hero,
    color: colors.brass,
    letterSpacing: 3,
    fontSize: 26,
  },
  body: { ...typography.body, color: colors.textSecondary, marginBottom: spacing.xl, lineHeight: 22 },
  memberRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xxl },
  memberDot: {
    width: 7, height: 7, borderRadius: 4, backgroundColor: colors.leaf, marginRight: spacing.sm,
  },
  memberText: { ...typography.subheading, color: colors.textPrimary },
  continueButton: {
    backgroundColor: colors.laterite, borderRadius: radii.pill, paddingVertical: 16, alignItems: "center",
  },
  continueButtonText: { ...typography.subheading, color: colors.sand },
});
