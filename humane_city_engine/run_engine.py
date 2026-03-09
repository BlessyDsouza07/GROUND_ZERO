"""
Main runner for Ground Zero City Intelligence Engine
"""

from utils.logger import get_logger

# Engine imports
from engine_2.context_engine import ContextEngine
from bias_guard.authenticity_score import AuthenticityScore

# External intelligence
from external_intelligence.review_intelligence_engine import ReviewIntelligenceEngine

# Live signals
from live_intelligence.crowd_intelligence_engine import CrowdIntelligenceEngine

# City special engine
from mangalore_special.mangalore_specialty_engine import MangaloreSpecialtyEngine


logger = get_logger("CityEngine")


def start_city_engine():

    logger.info("========================================")
    logger.info("Ground Zero City Intelligence Engine")
    logger.info("System starting...")
    logger.info("========================================")

    try:

        # Initialize Engines
        logger.info("Initializing Context Engine")
        context_engine = ContextEngine()

        logger.info("Initializing Authenticity Engine")
        authenticity_engine = AuthenticityScore()

        logger.info("Initializing Review Intelligence Engine")
        review_engine = ReviewIntelligenceEngine()

        logger.info("Initializing Crowd Intelligence Engine")
        crowd_engine = CrowdIntelligenceEngine()

        logger.info("Initializing Mangalore Specialty Engine")
        mangalore_engine = MangaloreSpecialtyEngine()

        logger.info("All engines initialized successfully")

        # Example place input
        place = {
            "name": "Panambur Beach",
            "category": "beach",
            "latitude": 12.995,
            "longitude": 74.786
        }

        user_context = {
            "time": "evening",
            "energy": "medium",
            "age_group": "adult"
        }

        logger.info("Running Context Evaluation")

        context_result = context_engine.evaluate_context(place, user_context)

        logger.info(f"Context Result: {context_result}")

        logger.info("Running Authenticity Scoring")

        authenticity_score = authenticity_engine.calculate_score(place)

        logger.info(f"Authenticity Score: {authenticity_score}")

        logger.info("Running Review Intelligence")

        review_signal = review_engine.analyze_place(place)

        logger.info(f"Review Intelligence: {review_signal}")

        logger.info("Running Crowd Intelligence")

        crowd_signal = crowd_engine.estimate_crowd(place)

        logger.info(f"Crowd Level: {crowd_signal}")

        logger.info("Running Mangalore Specialty Engine")

        specialty_score = mangalore_engine.evaluate_specialty(place)

        logger.info(f"Mangalore Specialty Score: {specialty_score}")

        logger.info("City Intelligence evaluation completed")

    except Exception as e:

        logger.error(f"City Engine crashed: {e}")


if __name__ == "__main__":

    start_city_engine()