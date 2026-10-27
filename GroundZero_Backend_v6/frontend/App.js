import React from "react";
import { View } from "react-native";
import { StatusBar } from "expo-status-bar";
import {
  useFonts,
  Fraunces_400Regular,
  Fraunces_500Medium,
  Fraunces_600SemiBold,
  Fraunces_600SemiBold_Italic,
} from "@expo-google-fonts/fraunces";
import {
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
} from "@expo-google-fonts/manrope";
import AppNavigator from "./src/navigation/AppNavigator";
import { colors } from "./src/theme/tokens";

export default function App() {
  const [fontsLoaded] = useFonts({
    Fraunces_400Regular,
    Fraunces_500Medium,
    Fraunces_600SemiBold,
    Fraunces_600SemiBold_Italic,
    Manrope_400Regular,
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
  });

  if (!fontsLoaded) {
    // A quiet, on-brand loading state rather than a stock spinner-on-white —
    // this is the very first thing a person sees, so it shouldn't break
    // the "silence by default" feel before the app has even opened.
    return <View style={{ flex: 1, backgroundColor: colors.deepTide }} />;
  }

  return (
    <>
      <StatusBar style="light" />
      <AppNavigator />
    </>
  );
}
