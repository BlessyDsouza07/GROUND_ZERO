"""
Phase 2 Implementation (Aug 4-5 2026): Enhanced API validation and security.

Adds:
1. Input validation (length limits, type checking)
2. Comprehensive error responses
3. Request/response validation schemas
4. Security headers
5. Input sanitization
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List


# === LAYER 0: PLACES API ===

class PlaceIn(BaseModel):
    """Input schema for creating/updating places."""
    name: str = Field(..., min_length=1, max_length=255, description="Place name")
    category: str = Field(..., min_length=1, max_length=100, description="Place category")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    tags: List[str] = Field(default_factory=list, max_items=50, description="Place tags (max 50)")
    description: Optional[str] = Field(None, max_length=5000, description="Place description (max 5000 chars)")
    
    @validator('name', 'category')
    def strip_whitespace(cls, v):
        """Strip leading/trailing whitespace."""
        if isinstance(v, str):
            return v.strip()
        return v
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate individual tags."""
        if v and len(v) > 50:
            raise ValueError('Maximum 50 tags allowed')
        return [tag.strip() for tag in v if tag.strip()]


class PlaceOut(BaseModel):
    """Output schema for places."""
    id: str
    name: str
    category: str
    latitude: float
    longitude: float
    estimated_cost: float
    price_band: str
    energy_requirement: str
    crowd_level: str
    bias_index: Optional[float]
    grade: Optional[str]
    tags: List[str]


# === LAYER 0: COMMUNITY SUBMISSIONS ===

class CommunitySubmissionIn(BaseModel):
    """Input schema for community place submissions."""
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    submitter_note: Optional[str] = Field(None, max_length=1000, description="Submitter notes (max 1000 chars)")
    tags: List[str] = Field(default_factory=list, max_items=50)
    
    @validator('submitter_note')
    def validate_note(cls, v):
        if v:
            return v.strip()
        return v


class CommunitySubmissionOut(BaseModel):
    """Output schema for submissions."""
    id: str
    status: str
    submitted_at: str
    reviewed_at: Optional[str]
    reviewed_by: Optional[str]


class SubmissionReviewIn(BaseModel):
    """Input for approving/rejecting submissions."""
    reviewed_by: str = Field(..., min_length=1, max_length=255, description="Admin name")
    notes: Optional[str] = Field(None, max_length=1000, description="Review notes")


# === LAYER 0: ADMIN ===

class AdminApiKeyIn(BaseModel):
    """Request body for admin operations requiring the API key."""
    admin_api_key: str = Field(..., min_length=10, max_length=255)


# === LAYER 1: SURVEY ===

class SurveyAnswerIn(BaseModel):
    """Input for survey answer."""
    question_index: int = Field(..., ge=0, le=20)
    answer: str = Field(..., min_length=1, max_length=500)


class SurveySessionOut(BaseModel):
    """Output for survey session state."""
    session_id: str
    current_step_index: int
    current_question: str
    options: List[str]


# === LAYER 2: HIVE ===

class RecommendationRequestIn(BaseModel):
    """Input for HIVE recommendation request."""
    profile_id: Optional[str] = Field(None, max_length=255)
    device_id: Optional[str] = Field(None, max_length=255)
    days_available: int = Field(default=1, ge=1, le=30, description="Days available (1-30)")
    budget_inr: float = Field(default=1000, ge=0, le=1000000, description="Budget in INR")


class RecommendationOut(BaseModel):
    """Output for HIVE recommendations."""
    recommendations: List[dict]
    reasoning: str
    optimal_order: List[str]


# === ERROR RESPONSES ===

class ErrorOut(BaseModel):
    """Standard error response."""
    error: str
    detail: str
    request_id: Optional[str] = None


class ValidationErrorOut(BaseModel):
    """Validation error response."""
    errors: List[dict]
    detail: str = "Validation failed"


class HealthOut(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    layers: List[str]
