import React, { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { colors } from "../theme/tokens";

/**
 * The Signal Ring — Ground Zero's signature element.
 *
 * A slow, quiet breathing ring rather than a spinner or a pulsing "loading"
 * indicator. It represents the guide's presence: it's there, it's paying
 * attention, but it isn't performing activity at you. This is the visual
 * expression of the product's "silence by default" philosophy — the ring
 * breathes at rest; it doesn't need to prove it's working.
 *
 * size: outer diameter in px. active: slightly brighter/faster breathing,
 * used to indicate a moment of real attention (e.g. right after the
 * tourist submits something) vs. the ambient idle state.
 */
export default function SignalRing({ size = 160, active = false }) {
  const breathe = useSharedValue(0);

  useEffect(() => {
    breathe.value = withRepeat(
      withTiming(1, {
        duration: active ? 1800 : 3400,
        easing: Easing.inOut(Easing.sin),
      }),
      -1,
      true
    );
  }, [active]);

  const outerStyle = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + breathe.value * 0.08 }],
    opacity: 0.35 + breathe.value * 0.25,
  }));

  const innerStyle = useAnimatedStyle(() => ({
    transform: [{ scale: 0.7 + breathe.value * 0.06 }],
    opacity: 0.6 + breathe.value * 0.4,
  }));

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      <Animated.View
        style={[
          styles.ring,
          outerStyle,
          { width: size, height: size, borderRadius: size / 2, borderColor: colors.brassDim },
        ]}
      />
      <Animated.View
        style={[
          styles.ring,
          innerStyle,
          {
            width: size * 0.62,
            height: size * 0.62,
            borderRadius: (size * 0.62) / 2,
            borderColor: colors.brass,
          },
        ]}
      />
      <View
        style={[
          styles.core,
          { width: size * 0.14, height: size * 0.14, borderRadius: (size * 0.14) / 2 },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", justifyContent: "center" },
  ring: { position: "absolute", borderWidth: 1.5 },
  core: { backgroundColor: colors.brass },
});
