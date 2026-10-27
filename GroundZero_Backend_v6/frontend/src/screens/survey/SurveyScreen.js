import React, { useEffect, useState } from "react";
import {
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeIn, FadeInRight, FadeOutLeft, Layout } from "react-native-reanimated";
import { SurveyApi } from "../../api/client";
import GlassCard from "../../components/GlassCard";
import Skeleton from "../../components/Skeleton";
import SignalRing from "../../components/SignalRing";
import { colors, radii, spacing, typography } from "../../theme/tokens";

const SINGLE_SELECT_OPTIONS = {
  q1_purpose: ["cultural", "foodie", "adventure", "leisure", "spiritual", "undecided"],
  q2_energy: ["low", "moderate", "high"],
  q3_crowd_tolerance: ["love_them", "fine", "prefer_quiet", "avoid_entirely"],
  q6_group_config: ["solo", "couple", "family", "friends"],
  q8_trip_duration: ["half_day", "full_day", "multi_day"],
  q9_start_time: ["morning", "mid_morning", "afternoon", "flexible"],
  voice_personality: ["warm_local_friend", "calm_historian", "witty_companion"],
  return_visitor_check: ["yes", "no"],
};

const MULTI_SELECT_OPTIONS = {
  q5_dietary: ["veg", "vegan", "no_beef", "halal", "no_restrictions"],
  accessibility: ["wheelchair", "limited_walking", "visual_impairment", "hearing_impairment", "none"],
};

const STEP_PROMPTS = {
  opening_prompt: "Tell me one honest thing — what are you hoping to do or find today?",
  q1_purpose: "What brings you here?",
  q2_energy: "How's your energy today?",
  q3_crowd_tolerance: "How do you feel about crowds?",
  q4_budget: "What's your budget for the day?",
  q5_dietary: "Any dietary things I should know?",
  q6_group_config: "Who's joining you?",
  accessibility: "Anything I should plan around?",
  q7_curiosity_text: "Tell me one honest thing you're curious about here.",
  q8_trip_duration: "How long do we have?",
  q9_start_time: "When do you want to start?",
  return_visitor_check: "Been here with me before? Want me to skip the spots you've already seen?",
  voice_personality: "Pick your guide's personality.",
  group_session_setup: "Share this code with the people joining you.",
};

// Steps the UI never shows. If a backend ever sends one of these (e.g. an
// older server build that still has the companion-language question), we
// answer it silently with the default instead of rendering a blank screen.
// Companion language defaults to English.
const AUTO_ANSWERED_STEPS = {
  companion_language: "english",
};

const OPTION_LABELS = {
  love_them: "I love them", fine: "I'm fine with them", prefer_quiet: "I prefer it quiet",
  avoid_entirely: "I'd rather avoid them", no_beef: "No beef", no_restrictions: "No restrictions",
  half_day: "Half day (~4 hrs)", full_day: "Full day (~8 hrs)", multi_day: "Multiple days",
  mid_morning: "Mid-morning", warm_local_friend: "Warm local friend", calm_historian: "Calm historian",
  witty_companion: "Witty companion", limited_walking: "Limited walking", visual_impairment: "Visual impairment",
  hearing_impairment: "Hearing impairment", yes: "Yes, skip them", no: "No, show me everything",
};

function optionLabel(opt) {
  return OPTION_LABELS[opt] || opt.replaceAll("_", " ");
}

export default function SurveyScreen({ onComplete, joinGroupSessionId }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [multiSelectDraft, setMultiSelectDraft] = useState([]);
  const [budgetDraft, setBudgetDraft] = useState("1500");
  const [curiosityDraft, setCuriosityDraft] = useState("");
  const [openingDraft, setOpeningDraft] = useState("");
  const [tripDaysDraft, setTripDaysDraft] = useState("2");
  const [showMultiDayInput, setShowMultiDayInput] = useState(false);

  useEffect(() => {
    SurveyApi.start(undefined, joinGroupSessionId)
      .then((s) => {
        setSession(s);
        setMultiSelectDraft([]);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Silently answer any step in AUTO_ANSWERED_STEPS and move on.
  const currentStep = session?.current_step;
  useEffect(() => {
    if (!session || submitting || error) return;
    if (Object.prototype.hasOwnProperty.call(AUTO_ANSWERED_STEPS, currentStep)) {
      submitAnswer(AUTO_ANSWERED_STEPS[currentStep]);
    }
  }, [currentStep]);

  async function submitAnswer(answer) {
    if (!session) return;
    setSubmitting(true);
    try {
      const next = await SurveyApi.answer(session.session_id, answer);
      setMultiSelectDraft([]);
      setShowMultiDayInput(false);
      setOpeningDraft("");
      if (next.is_complete) {
        const profile = await SurveyApi.finalize(session.session_id);
        onComplete?.(profile);
      } else {
        setSession(next);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleMultiSelect(value) {
    setMultiSelectDraft((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    );
  }

  if (error) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.center}>
        <Text style={styles.errorText}>Something went wrong: {error}</Text>
      </LinearGradient>
    );
  }

  if (loading || Object.prototype.hasOwnProperty.call(AUTO_ANSWERED_STEPS, session?.current_step)) {
    return (
      <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.container}>
        <View style={{ marginTop: spacing.xxxl, marginBottom: spacing.xl }}>
          <Skeleton width={220} height={16} borderRadius={4} />
        </View>
        <Skeleton width={"100%"} height={30} borderRadius={6} style={{ marginBottom: spacing.xl }} />
        <Skeleton width={"100%"} height={52} style={{ marginBottom: spacing.sm }} />
        <Skeleton width={"100%"} height={52} style={{ marginBottom: spacing.sm }} />
        <Skeleton width={"100%"} height={52} />
      </LinearGradient>
    );
  }

  const step = session?.current_step;
  const prompt = STEP_PROMPTS[step] || step?.replaceAll("_", " ");

  return (
    <LinearGradient colors={[colors.deepTideDeeper, colors.deepTide]} style={styles.container}>
      <View style={styles.header}>
        <View style={styles.progressTrack}>
          <Animated.View
            layout={Layout.duration(400)}
            style={[styles.progressFill, { width: `${(session?.progress_fraction || 0) * 100}%` }]}
          />
        </View>
        <View style={styles.presenceIndicator}>
          <SignalRing size={28} active={submitting} />
        </View>
      </View>

      <Animated.View
        key={step}
        entering={FadeInRight.duration(320)}
        exiting={FadeOutLeft.duration(200)}
        style={styles.questionArea}
      >
        <Text style={styles.heading}>{prompt}</Text>

        {SINGLE_SELECT_OPTIONS[step] && !(step === "q8_trip_duration" && showMultiDayInput) && (
          <View>
            {SINGLE_SELECT_OPTIONS[step].map((opt, i) => (
              <Animated.View key={opt} entering={FadeIn.delay(60 * i).duration(300)}>
                <TouchableOpacity
                  style={styles.optionCard}
                  activeOpacity={0.7}
                  disabled={submitting}
                  onPress={() => {
                    if (step === "q8_trip_duration" && opt === "multi_day") {
                      setShowMultiDayInput(true);
                      return;
                    }
                    submitAnswer(step === "return_visitor_check" ? opt === "yes" : opt);
                  }}
                >
                  <Text style={styles.optionText}>{optionLabel(opt)}</Text>
                </TouchableOpacity>
              </Animated.View>
            ))}
          </View>
        )}

        {step === "q8_trip_duration" && showMultiDayInput && (
          <GlassCard>
            <TextInput
              style={styles.textInput}
              keyboardType="numeric"
              value={tripDaysDraft}
              onChangeText={setTripDaysDraft}
              placeholder="Number of days"
              placeholderTextColor={colors.textFaint}
            />
            <TouchableOpacity
              style={styles.continueButton}
              onPress={() => submitAnswer({ duration: "multi_day", days: Number(tripDaysDraft) || 2 })}
            >
              <Text style={styles.continueButtonText}>Continue</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {MULTI_SELECT_OPTIONS[step] && (
          <View>
            {MULTI_SELECT_OPTIONS[step].map((opt, i) => {
              const selected = multiSelectDraft.includes(opt);
              return (
                <Animated.View key={opt} entering={FadeIn.delay(60 * i).duration(300)}>
                  <TouchableOpacity
                    style={[styles.optionCard, selected && styles.optionCardSelected]}
                    activeOpacity={0.7}
                    onPress={() => toggleMultiSelect(opt)}
                  >
                    <View style={[styles.checkDot, selected && styles.checkDotFilled]} />
                    <Text style={styles.optionText}>{optionLabel(opt)}</Text>
                  </TouchableOpacity>
                </Animated.View>
              );
            })}
            <TouchableOpacity
              style={styles.continueButton}
              disabled={submitting}
              onPress={() => submitAnswer(multiSelectDraft)}
            >
              <Text style={styles.continueButtonText}>
                {multiSelectDraft.length > 0 ? "Continue" : "None of these — continue"}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {step === "q4_budget" && (
          <GlassCard>
            <TextInput
              style={styles.textInput}
              keyboardType="numeric"
              value={budgetDraft}
              onChangeText={setBudgetDraft}
              placeholder="e.g. 1500"
              placeholderTextColor={colors.textFaint}
            />
            <Text style={styles.caption}>Total, in rupees, for the whole day.</Text>
            <TouchableOpacity
              style={styles.continueButton}
              disabled={submitting}
              onPress={() => submitAnswer(Number(budgetDraft) || 0)}
            >
              <Text style={styles.continueButtonText}>Continue</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {step === "opening_prompt" && (
          <GlassCard>
            <TextInput
              style={[styles.textInput, styles.textArea]}
              value={openingDraft}
              onChangeText={setOpeningDraft}
              placeholder="e.g. I want quiet local food and old churches, not tourist traps"
              placeholderTextColor={colors.textFaint}
              multiline
            />
            <Text style={styles.caption}>
              This one sentence can skip several of the questions below — I'll only ask what I still need.
            </Text>
            <TouchableOpacity
              style={[styles.continueButton, !openingDraft.trim() && styles.continueButtonDisabled]}
              disabled={!openingDraft.trim() || submitting}
              onPress={() => submitAnswer(openingDraft)}
            >
              <Text style={styles.continueButtonText}>Continue</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {step === "q7_curiosity_text" && (
          <GlassCard>
            <TextInput
              style={[styles.textInput, styles.textArea]}
              value={curiosityDraft}
              onChangeText={setCuriosityDraft}
              placeholder="e.g. I want to find quiet local food, not tourist traps"
              placeholderTextColor={colors.textFaint}
              multiline
            />
            <TouchableOpacity
              style={[styles.continueButton, !curiosityDraft.trim() && styles.continueButtonDisabled]}
              disabled={!curiosityDraft.trim() || submitting}
              onPress={() => submitAnswer(curiosityDraft)}
            >
              <Text style={styles.continueButtonText}>Continue</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {step === "group_session_setup" && (
          <GlassCard>
            <Text style={styles.body}>
              Once you finish, you'll get a code to share with your group. Each person completes
              their own quick survey and joins with that code.
            </Text>
            <TouchableOpacity style={styles.continueButton} onPress={() => submitAnswer(true)}>
              <Text style={styles.continueButtonText}>Got it — continue</Text>
            </TouchableOpacity>
          </GlassCard>
        )}
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.lg, paddingTop: spacing.xxl },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  errorText: { ...typography.body, color: colors.textSecondary, textAlign: "center" },

  header: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xl, gap: spacing.md },
  progressTrack: { flex: 1, height: 2, backgroundColor: colors.border, borderRadius: 1 },
  progressFill: { height: 2, backgroundColor: colors.brass, borderRadius: 1 },
  presenceIndicator: { width: 28, height: 28 },

  questionArea: { flex: 1 },
  heading: { ...typography.heading, color: colors.textPrimary, marginBottom: spacing.lg },
  body: { ...typography.body, color: colors.textSecondary, marginBottom: spacing.md },
  caption: { ...typography.caption, color: colors.textFaint, marginTop: spacing.xs, marginBottom: spacing.md },

  optionCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(241,230,210,0.05)",
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  optionCardSelected: { borderColor: colors.brass, backgroundColor: "rgba(201,162,83,0.08)" },
  optionText: { ...typography.subheading, color: colors.textPrimary, textTransform: "capitalize" },
  checkDot: {
    width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.textFaint,
    marginRight: spacing.sm,
  },
  checkDotFilled: { backgroundColor: colors.brass, borderColor: colors.brass },

  textInput: {
    backgroundColor: "rgba(241,230,210,0.06)",
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    color: colors.textPrimary,
    ...typography.body,
  },
  textArea: { minHeight: 100, textAlignVertical: "top" },

  continueButton: {
    backgroundColor: colors.laterite,
    borderRadius: radii.pill,
    paddingVertical: 15,
    alignItems: "center",
    marginTop: spacing.md,
  },
  continueButtonDisabled: { opacity: 0.35 },
  continueButtonText: { ...typography.subheading, color: colors.sand },
});
