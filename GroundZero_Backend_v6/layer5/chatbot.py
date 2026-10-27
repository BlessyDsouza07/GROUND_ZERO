"""
Layer 5 Feature: Tourism Chatbot

Phase 7 Implementation (Aug 5 2026): Conversational AI assistant
Handles:
- Q&A about places
- Nearby discovery
- Trip planning
- Emergency services
- General tourism info

Uses intent classification + response generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only, avoids a hard
    # dependency from layer5 -> layer0/layer1/layer2 at module load time.
    from layer0.domain.repositories import PlaceRepository
    from layer1.domain.entities import TouristProfile
    from layer2.application.hive_engine import HiveEngine

logger = logging.getLogger("groundzero.layer5.chatbot")


def _place_to_dict(place) -> dict:
    """Map a Layer 0 `Place` domain entity to the plain dict shape the
    chatbot/API layer works with, without pulling a hard import of
    `layer0.domain.entities.Place` into this module."""
    return {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "latitude": place.coordinates.latitude,
        "longitude": place.coordinates.longitude,
        "description": place.description,
        "estimated_cost": place.estimated_cost,
        "bias_index": place.bias_index,
        "grade": place.grade.value if place.grade else None,
    }


class ChatIntent(str, Enum):
    """Intent categories for chat messages."""
    SEARCH_PLACE = "search_place"
    GET_INFO = "get_info"
    RECOMMEND = "recommend"
    NEARBY = "nearby"
    EMERGENCY = "emergency"
    DIRECTIONS = "directions"
    HOURS = "hours"
    PRICE = "price"
    ACTIVITY = "activity"
    GREETING = "greeting"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ChatMessage:
    """Chat message in conversation."""
    sender: str  # "user" or "bot"
    text: str
    timestamp: datetime
    intent: Optional[ChatIntent] = None
    confidence: float = 0.0


class IntentClassifier:
    """Classifies user queries into intents."""

    async def classify(self, text: str) -> tuple[ChatIntent, float]:
        """
        Classify message intent.
        
        Returns:
            (intent, confidence_score)
        """
        text_lower = text.lower()

        # Define keywords for each intent
        intent_keywords = {
            ChatIntent.NEARBY: ["near", "nearby", "close", "around here", "what's close"],
            ChatIntent.EMERGENCY: ["emergency", "help", "police", "hospital", "ambulance", "911"],
            ChatIntent.DIRECTIONS: ["how to get", "directions", "navigate", "way to", "route"],
            ChatIntent.HOURS: ["hours", "open", "closed", "when", "timing", "schedule"],
            ChatIntent.PRICE: ["price", "cost", "fee", "how much", "expensive", "cheap"],
            ChatIntent.ACTIVITY: ["activity", "do", "activities", "what to do", "things to do"],
            ChatIntent.RECOMMEND: ["recommend", "suggest", "what should", "best", "top"],
            ChatIntent.SEARCH_PLACE: ["find", "show", "search", "look for", "where"],
            ChatIntent.GET_INFO: ["tell me", "info", "about", "details", "facts"],
            ChatIntent.GREETING: ["hello", "hi", "hey", "greetings", "namaste"],
            ChatIntent.HELP: ["help", "guide", "tutorial", "how do", "explain"],
        }

        # Find matching intent
        best_intent = ChatIntent.UNKNOWN
        best_score = 0.0

        for intent, keywords in intent_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            if matches > 0:
                score = matches / len(keywords)
                if score > best_score:
                    best_intent = intent
                    best_score = score

        logger.debug("Classified intent: %s (confidence: %.1f)", best_intent, best_score)
        return best_intent, best_score


class ContextManager:
    """Manages conversation context for coherent responses."""

    def __init__(self, max_history: int = 10):
        self.conversation_history: List[ChatMessage] = []
        self.current_place: Optional[dict] = None
        self.current_category: Optional[str] = None
        self.max_history = max_history

    def add_message(self, message: ChatMessage) -> None:
        """Add message to conversation history."""
        self.conversation_history.append(message)
        
        # Keep only recent messages
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

    def get_context(self) -> dict:
        """Get current conversation context."""
        return {
            "current_place": self.current_place,
            "current_category": self.current_category,
            "message_count": len(self.conversation_history),
            "last_messages": self.conversation_history[-3:],
        }


class ResponseGenerator:
    """Generates bot responses based on intent and context."""

    async def generate(self, intent: ChatIntent, context: dict) -> str:
        """Generate response for given intent."""
        
        responses = {
            ChatIntent.GREETING: [
                "Namaste! Welcome to Ground Zero. How can I help you explore Mangalore?",
                "Hello! I'm your tourism guide. What would you like to discover?",
                "Hi there! Ready to explore some amazing places?",
            ],
            ChatIntent.HELP: [
                "I can help you find places, get recommendations, navigate, and answer questions. What would you like to do?",
                "Try asking me: 'Show me temples', 'What's nearby?', 'How do I get there?', or 'Tell me about this place'.",
            ],
            ChatIntent.SEARCH_PLACE: [
                "I'll search for that place for you. Which type of place are you looking for?",
                "Let me find that for you. What category interests you?",
            ],
            ChatIntent.NEARBY: [
                "Let me show you what's nearby. What kind of places interest you?",
                "There are some great places close by! What would you like to explore?",
            ],
            # BUG FIX (6th audit response, Oct 2026): these quoted the old
            # separate police/ambulance/fire numbers; layer3_i18n.py's
            # safety_sos strings already use India's unified pan-India
            # emergency number (112, covers police/fire/health) in all 4
            # languages -- this was the one place left behind.
            ChatIntent.EMERGENCY: [
                "In case of emergency, call 112 — India's unified emergency number for police, fire, and ambulance.",
                "Emergency services: call 112 any time, for police, fire, or ambulance. Stay safe!",
            ],
            ChatIntent.UNKNOWN: [
                "I didn't quite understand that. Could you rephrase?",
                "Can you tell me more about what you're looking for?",
                "Try asking about places, recommendations, or nearby attractions!",
            ],
        }

        # Get response template for intent
        intent_responses = responses.get(intent, responses[ChatIntent.UNKNOWN])
        response = intent_responses[0]  # In production: random selection

        logger.info("Generated response for %s: %s", intent, response[:50])
        return response


class TourismChatbot:
    """
    Main chatbot class coordinating intent classification and response generation.
    """

    def __init__(
        self,
        place_repository: "Optional[PlaceRepository]" = None,
        hive_engine: "Optional[HiveEngine]" = None,
    ):
        self.classifier = IntentClassifier()
        self.generator = ResponseGenerator()
        self.context = ContextManager()
        # Bug fixed: these were always `None` stubs (see class docstring
        # in the old version) — every real-data method below silently
        # returned `[]`/`None` no matter what was asked, because nothing
        # ever set these after construction. Now injected from
        # `layer5/api/dependencies.py`, backed by the real Layer 0 place
        # repository and Layer 2 HIVE engine.
        self.place_repository = place_repository
        self.hive_engine = hive_engine

    async def process_message(self, user_message: str) -> tuple[str, ChatMessage]:
        """
        Process user message and generate bot response.
        
        Returns:
            (bot_response_text, bot_message_object)
        """
        # Record user message
        user_msg = ChatMessage(
            sender="user",
            text=user_message,
            timestamp=datetime.now(),
        )
        self.context.add_message(user_msg)

        # Classify intent
        intent, confidence = await self.classifier.classify(user_message)
        user_msg.intent = intent
        user_msg.confidence = confidence

        # Generate response
        context_info = self.context.get_context()
        response_text = await self.generator.generate(intent, context_info)

        # Record bot message
        bot_msg = ChatMessage(
            sender="bot",
            text=response_text,
            timestamp=datetime.now(),
            intent=intent,
            confidence=confidence,
        )
        self.context.add_message(bot_msg)

        return response_text, bot_msg

    async def search_places(self, query: str, category: Optional[str] = None) -> List[dict]:
        """
        Search for places based on user query.

        Real implementation: pulls the full Layer 0 catalog (optionally
        pre-filtered by category, since `PlaceRepository.list_all` already
        supports that) and does a case-insensitive substring match against
        name/description/tags — the same "no fabrication" rule as the rest
        of the codebase applies here: if the repository isn't wired up,
        this returns `[]` rather than making up a place.
        """
        if self.place_repository is None:
            logger.warning("search_places called with no place_repository configured")
            return []

        logger.info("Searching places: %s (category: %s)", query, category)
        places = await self.place_repository.list_all(category=category)
        needle = query.strip().lower()
        if not needle:
            matches = places
        else:
            matches = [
                p
                for p in places
                if needle in p.name.lower()
                or (p.description and needle in p.description.lower())
                or any(needle in t.lower() for t in p.tags)
            ]
        return [_place_to_dict(p) for p in matches]

    async def get_nearby_places(self, latitude: float, longitude: float, radius_m: int = 500) -> List[dict]:
        """
        Get places nearby user location, sorted closest-first.

        Real implementation: reuses the geofencing engine's haversine
        distance calculation (`layer5.geofencing.GPSCoordinate.distance_to`)
        against every place from the repository, rather than the old
        always-empty stub.
        """
        if self.place_repository is None:
            logger.warning("get_nearby_places called with no place_repository configured")
            return []

        from layer5.geofencing import GPSCoordinate  # local import: avoids a
        # module-level layer5.chatbot <-> layer5.geofencing import cycle risk

        logger.info("Getting nearby places at (%.4f, %.4f), radius: %dm", latitude, longitude, radius_m)
        origin = GPSCoordinate(latitude=latitude, longitude=longitude, accuracy_m=0.0, timestamp=datetime.now(timezone.utc))
        places = await self.place_repository.list_all()
        with_distance = [
            (p, origin.distance_to(p.coordinates.latitude, p.coordinates.longitude)) for p in places
        ]
        nearby = sorted((pd for pd in with_distance if pd[1] <= radius_m), key=lambda pd: pd[1])
        return [{**_place_to_dict(p), "distance_meters": round(d, 1)} for p, d in nearby]

    async def get_place_info(self, place_id: str) -> Optional[dict]:
        """
        Get detailed information about a place.
        """
        if self.place_repository is None:
            logger.warning("get_place_info called with no place_repository configured")
            return None

        logger.info("Getting info for place: %s", place_id)
        place = await self.place_repository.get_by_id(place_id)
        return _place_to_dict(place) if place is not None else None

    async def get_recommendations(self, profile_id: str, profile: "Optional[TouristProfile]" = None) -> List[dict]:
        """
        Get personalized recommendations for user via the real Layer 2
        HIVE engine.

        `profile` must be supplied by the caller (the API route loads it
        from the TouristProfile repository) — the chatbot itself has no
        profile storage, so it cannot look one up from just an id.
        """
        if self.hive_engine is None:
            logger.warning("get_recommendations called with no hive_engine configured")
            return []
        if profile is None:
            logger.warning("get_recommendations called for profile %s with no profile object supplied", profile_id)
            return []

        logger.info("Getting recommendations for profile: %s", profile_id)
        queue = await self.hive_engine.build_recommendation_queue(profile, datetime.now(timezone.utc))
        return [
            {
                "place_id": item.place_id,
                "place_name": item.place_name,
                "role": item.role.value,
                "scheduled_time": item.scheduled_time.isoformat(),
                "reason_selected": item.reason_selected,
                "personal_score": item.personal_score,
            }
            for item in queue.items
        ]

    def get_conversation_history(self) -> List[ChatMessage]:
        """Get full conversation history."""
        return self.context.conversation_history

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.context.conversation_history = []
        logger.info("Conversation history cleared")
