import React from "react";
import { StyleSheet, View } from "react-native";
import { BlurView } from "expo-blur";
import { radii, shadow } from "../theme/tokens";

/**
 * A frosted, warm-tinted glass surface — used wherever content needs to
 * float above the deep-tide background without becoming a flat opaque
 * card. The blur + faint sand tint is what makes it read as "glass" over
 * a gradient rather than just a rounded rectangle.
 */
export default function GlassCard({ children, style, intensity = 24 }) {
  return (
    <View style={[styles.wrapper, shadow.soft, style]}>
      <BlurView intensity={intensity} tint="dark" style={StyleSheet.absoluteFill} />
      <View style={styles.tint} pointerEvents="none" />
      <View style={styles.content}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    borderRadius: radii.lg,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(241,230,210,0.12)",
  },
  tint: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(241,230,210,0.04)",
  },
  content: {
    padding: 20,
  },
});
