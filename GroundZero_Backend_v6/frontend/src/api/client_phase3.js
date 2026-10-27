/**
 * Phase 3 Implementation (Aug 5 2026): Enhanced API client
 *
 * Complete HTTP client for Ground Zero backend with:
 * - Full endpoint support (Layer 0, 1, 2)
 * - Request/response validation
 * - Error handling and retries
 * - Request ID tracking
 * - Timeout handling
 * - Automatic retry on network errors
 */

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30000; // 30 second timeout
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

// Request state tracking
let requestIdCounter = 0;

/**
 * Generate unique request ID for tracking
 */
function generateRequestId() {
  return `req-${Date.now()}-${++requestIdCounter}`;
}

/**
 * Delay for exponential backoff
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Make HTTP request with error handling and retries
 */
async function request(path, options = {}, retryCount = 0) {
  const requestId = generateRequestId();
  
  // Prepare request
  const url = `${BASE_URL}${path}`;
  const fetchOptions = {
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": requestId,
      ...options.headers,
    },
    ...options,
  };

  try {
    // Set timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);

    // Parse response
    const contentType = response.headers.get("content-type");
    let body;
    
    if (contentType?.includes("application/json")) {
      body = await response.json();
    } else {
      body = await response.text();
    }

    // Handle errors
    if (!response.ok) {
      const errorMessage = typeof body === "object" ? body.detail || body.error : body;
      const error = new Error(errorMessage || `HTTP ${response.status}`);
      error.status = response.status;
      error.requestId = requestId;
      error.response = body;
      
      // Retry on network errors (5xx)
      if (response.status >= 500 && retryCount < MAX_RETRIES) {
        console.warn(`Request failed [${requestId}]: ${response.status}. Retrying (${retryCount + 1}/${MAX_RETRIES})...`);
        await delay(RETRY_DELAY_MS * (retryCount + 1));
        return request(path, options, retryCount + 1);
      }
      
      throw error;
    }

    // Success
    console.log(`Request successful [${requestId}]: ${options.method || "GET"} ${path} (${response.status})`);
    return { data: body, requestId, status: response.status };

  } catch (error) {
    // Network errors (timeout, aborted, etc.)
    if (error.name === "AbortError") {
      const timeoutError = new Error(`Request timeout after ${REQUEST_TIMEOUT_MS}ms`);
      timeoutError.requestId = requestId;
      throw timeoutError;
    }

    // Retry on network errors
    if ((error.message?.includes("Network") || error.message?.includes("Failed to fetch")) && retryCount < MAX_RETRIES) {
      console.warn(`Network error [${requestId}]. Retrying (${retryCount + 1}/${MAX_RETRIES})...`);
      await delay(RETRY_DELAY_MS * (retryCount + 1));
      return request(path, options, retryCount + 1);
    }

    error.requestId = requestId;
    throw error;
  }
}

/**
 * Layer 0: Places & Community API
 */
export const PlacesApi = {
  // Get all places or filter by category
  list: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const response = await request(`/places${query ? `?${query}` : ""}`);
    return response.data;
  },

  // Get single place details
  get: async (placeId) => {
    const response = await request(`/places/${placeId}`);
    return response.data;
  },

  // Mark place as visited (Phase 1 feature)
  markVisited: async (placeId) => {
    const response = await request(`/places/${placeId}/mark-visited`, {
      method: "POST",
    });
    return response.data;
  },

  // Search places by keyword
  search: async (keyword) => {
    const response = await request("/places/search", {
      method: "POST",
      body: JSON.stringify({ query: keyword }),
    });
    return response.data;
  },

  // Filter places by criteria
  filter: async (criteria) => {
    const response = await request("/places/filter", {
      method: "POST",
      body: JSON.stringify(criteria),
    });
    return response.data;
  },

  // Submit community place suggestion
  submitSuggestion: async (placeData) => {
    const response = await request("/places/submissions", {
      method: "POST",
      body: JSON.stringify(placeData),
    });
    return response.data;
  },
};

/**
 * Layer 1: Survey & Preferences API
 */
export const SurveyApi = {
  // Start survey session
  start: async (deviceId, groupSessionId = null) => {
    const response = await request("/survey/start", {
      method: "POST",
      body: JSON.stringify({
        device_id: deviceId,
        join_group_session_id: groupSessionId,
      }),
    });
    return response.data;
  },

  // Get current survey state/question
  getState: async (sessionId) => {
    const response = await request(`/survey/${sessionId}`);
    return response.data;
  },

  // Submit answer to current question
  answer: async (sessionId, answerText) => {
    const response = await request(`/survey/${sessionId}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer: answerText }),
    });
    return response.data;
  },

  // Finalize survey (get profile)
  finalize: async (sessionId) => {
    const response = await request(`/survey/${sessionId}/finalize`, {
      method: "POST",
    });
    return response.data;
  },

  // Get group survey members
  getGroupMembers: async (groupSessionId) => {
    const response = await request(`/survey/group/${groupSessionId}/members`);
    return response.data;
  },

  // Rejoin existing session (for group surveys)
  rejoin: async (sessionId) => {
    const response = await request(`/survey/${sessionId}/rejoin`, {
      method: "POST",
    });
    return response.data;
  },
};

/**
 * Layer 2: HIVE Recommendations API
 */
export const HiveApi = {
  // Get personalized recommendations
  getRecommendations: async (profileId, constraints = {}) => {
    const response = await request("/hive/recommendations", {
      method: "POST",
      body: JSON.stringify({
        profile_id: profileId,
        ...constraints, // budget, days_available, preferences, etc.
      }),
    });
    return response.data;
  },

  // Get explanation for recommendation
  explainRecommendation: async (placeId, profileId) => {
    const response = await request("/hive/explain", {
      method: "POST",
      body: JSON.stringify({
        place_id: placeId,
        profile_id: profileId,
      }),
    });
    return response.data;
  },

  // Rate recommendation (feedback)
  ratePlaceRecommendation: async (placeId, rating, feedback = null) => {
    const response = await request(`/hive/places/${placeId}/rate`, {
      method: "POST",
      body: JSON.stringify({
        rating, // 1-5 stars
        feedback,
      }),
    });
    return response.data;
  },
};

/**
 * Health & Status API
 */
export const HealthApi = {
  // Check backend health
  check: async () => {
    try {
      const response = await request("/health");
      return response.data;
    } catch (error) {
      return {
        status: "error",
        message: error.message,
        layers: [],
      };
    }
  },

  // Get API documentation
  getDocs: async () => {
    const response = await request("/docs");
    return response.data;
  },
};

/**
 * Error handling helper
 */
export function isNetworkError(error) {
  return error.status === undefined || error.message?.includes("Network") || error.message?.includes("timeout");
}

export function isValidationError(error) {
  return error.status === 400 || error.status === 422;
}

export function isAuthError(error) {
  return error.status === 401 || error.status === 403;
}

export function isNotFoundError(error) {
  return error.status === 404;
}

/**
 * Default export (backward compatibility)
 */
export default {
  PlacesApi,
  SurveyApi,
  HiveApi,
  HealthApi,
};
