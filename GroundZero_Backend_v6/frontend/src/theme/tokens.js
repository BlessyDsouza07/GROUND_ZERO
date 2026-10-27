/**
 * Design tokens for Ground Zero.
 *
 * Every color traces to something specific in coastal Karnataka rather
 * than being picked abstractly: deep-tide is the Arabian Sea at dusk,
 * laterite is the region's iconic red-clay roof tile, brass is temple
 * hardware, leaf is monsoon greenery. Type pairing is Fraunces (an
 * editorial serif with deliberately organic, hand-cut curves — used for
 * the app's one moment of personality) against Manrope (a clean humanist
 * sans for everything that needs to just be legible).
 */
export const colors = {
  deepTide: "#0D2B2B",
  deepTideDeeper: "#081D1D", // for gradient depth, not a flat fill
  surface: "#123636",
  surfaceRaised: "#17403F",
  border: "#1E4D4B",

  laterite: "#C1602E",
  lateriteDim: "#8A4622",
  brass: "#C9A253",
  brassDim: "#8C7239",
  leaf: "#5C7A52",

  sand: "#F1E6D2",
  sandDim: "#D8C9AC",

  textPrimary: "#F1E6D2",
  textSecondary: "#A9BDBA",
  textFaint: "#5F7B78",
  textOnSand: "#1C2320",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
};

// Font family keys match the useFonts() keys loaded in App.js via
// @expo-google-fonts — every screen references these constants rather
// than hardcoding family strings.
export const fontFamily = {
  displayRegular: "Fraunces_400Regular",
  displayMedium: "Fraunces_500Medium",
  displaySemiBold: "Fraunces_600SemiBold",
  displaySemiBoldItalic: "Fraunces_600SemiBold_Italic",
  bodyRegular: "Manrope_400Regular",
  bodyMedium: "Manrope_500Medium",
  bodySemiBold: "Manrope_600SemiBold",
  bodyBold: "Manrope_700Bold",
};

export const typography = {
  // The italic Fraunces face is the app's one flourish, reserved for the
  // hero moment (Start screen) — everywhere else uses the upright weights,
  // so the italic keeps its impact instead of becoming the default look.
  hero: { fontFamily: fontFamily.displaySemiBoldItalic, fontSize: 34, lineHeight: 40 },
  heading: { fontFamily: fontFamily.displayMedium, fontSize: 26, lineHeight: 32 },
  subheading: { fontFamily: fontFamily.bodySemiBold, fontSize: 17, lineHeight: 24 },
  body: { fontFamily: fontFamily.bodyRegular, fontSize: 15, lineHeight: 22 },
  bodyMedium: { fontFamily: fontFamily.bodyMedium, fontSize: 15, lineHeight: 22 },
  caption: { fontFamily: fontFamily.bodyRegular, fontSize: 12.5, lineHeight: 18 },
  label: { fontFamily: fontFamily.bodySemiBold, fontSize: 11, letterSpacing: 1.2 },
};

export const radii = {
  sm: 10,
  md: 18,
  lg: 28,
  pill: 999,
};

export const shadow = {
  soft: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 6,
  },
};
