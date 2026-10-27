/**
 * Phase 3 Implementation: useSurveyFlow hook
 *
 * Manages complete survey flow state:
 * - Survey session management
 * - Question progression
 * - Profile generation
 * - Error handling
 * - Loading states
 */

import { useState, useCallback, useRef } from "react";
import { SurveyApi, PlacesApi } from "../api/client_phase3";

/**
 * Survey state machine states
 */
export const SURVEY_STATES = {
  INITIAL: "initial",
  LOADING: "loading",
  QUESTION: "question",
  COMPLETE: "complete",
  ERROR: "error",
};

/**
 * Hook for managing survey flow
 */
export function useSurveyFlow() {
  const [state, setState] = useState(SURVEY_STATES.INITIAL);
  const [sessionId, setSessionId] = useState(null);
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState([]);
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const deviceIdRef = useRef(null);

  /**
   * Start survey session
   */
  const startSurvey = useCallback(async (deviceId) => {
    setIsLoading(true);
    setError(null);
    deviceIdRef.current = deviceId;

    try {
      setState(SURVEY_STATES.LOADING);
      const response = await SurveyApi.start(deviceId);
      
      setSessionId(response.session_id);
      setCurrentQuestion(response.current_question);
      setQuestionIndex(response.current_step_index);
      setAnswers([]);
      setState(SURVEY_STATES.QUESTION);
    } catch (err) {
      setError({
        message: err.message,
        requestId: err.requestId,
      });
      setState(SURVEY_STATES.ERROR);
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Submit answer to current question and move to next
   */
  const submitAnswer = useCallback(async (answerText) => {
    if (!sessionId) {
      setError({ message: "No active survey session" });
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      setState(SURVEY_STATES.LOADING);

      // Submit answer
      const response = await SurveyApi.answer(sessionId, answerText);
      
      // Store answer
      setAnswers(prev => [...prev, answerText]);

      // Check if survey is complete
      if (response.completed) {
        // Finalize to get profile
        const profileResponse = await SurveyApi.finalize(sessionId);
        setProfile(profileResponse);
        setState(SURVEY_STATES.COMPLETE);
      } else {
        // Move to next question
        setCurrentQuestion(response.current_question);
        setQuestionIndex(response.current_step_index);
        setState(SURVEY_STATES.QUESTION);
      }
    } catch (err) {
      setError({
        message: err.message,
        requestId: err.requestId,
        isNetworkError: err.status === undefined,
      });
      setState(SURVEY_STATES.ERROR);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  /**
   * Restart survey (go back to initial state)
   */
  const restart = useCallback(() => {
    setState(SURVEY_STATES.INITIAL);
    setSessionId(null);
    setCurrentQuestion(null);
    setQuestionIndex(0);
    setAnswers([]);
    setProfile(null);
    setError(null);
  }, []);

  /**
   * Retry after error
   */
  const retry = useCallback(async () => {
    setError(null);
    
    if (sessionId) {
      // We're mid-survey, try to resume
      try {
        const response = await SurveyApi.getState(sessionId);
        setCurrentQuestion(response.current_question);
        setQuestionIndex(response.current_step_index);
        setState(SURVEY_STATES.QUESTION);
      } catch (err) {
        setError({
          message: "Failed to resume survey: " + err.message,
          requestId: err.requestId,
        });
      }
    }
  }, [sessionId]);

  return {
    // State
    state,
    sessionId,
    currentQuestion,
    questionIndex,
    answers,
    profile,
    error,
    isLoading,
    progress: questionIndex / 9, // Assuming 9 questions

    // Actions
    startSurvey,
    submitAnswer,
    restart,
    retry,
  };
}

/**
 * Hook for managing place recommendations
 */
export function useRecommendations() {
  const [recommendations, setRecommendations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  /**
   * Get recommendations for profile
   */
  const getRecommendations = useCallback(async (profileId, constraints = {}) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await PlacesApi.filter({
        profile_id: profileId,
        ...constraints,
      });
      setRecommendations(response.recommendations || response);
    } catch (err) {
      setError({
        message: err.message,
        requestId: err.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Mark place as visited
   */
  const markVisited = useCallback(async (placeId) => {
    try {
      await PlacesApi.markVisited(placeId);
      // Update local state
      setRecommendations(prev =>
        prev.map(place =>
          place.id === placeId ? { ...place, visited: true } : place
        )
      );
    } catch (err) {
      setError({
        message: "Failed to mark place as visited: " + err.message,
        requestId: err.requestId,
      });
    }
  }, []);

  return {
    recommendations,
    isLoading,
    error,
    getRecommendations,
    markVisited,
  };
}

/**
 * Hook for managing places search
 */
export function usePlacesSearch() {
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  /**
   * Search places
   */
  const search = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    setSearchQuery(query);

    try {
      const response = await PlacesApi.search(query);
      setResults(response.results || response);
    } catch (err) {
      setError({
        message: err.message,
        requestId: err.requestId,
      });
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Clear search
   */
  const clear = useCallback(() => {
    setResults([]);
    setSearchQuery("");
    setError(null);
  }, []);

  return {
    results,
    isLoading,
    error,
    searchQuery,
    search,
    clear,
  };
}
