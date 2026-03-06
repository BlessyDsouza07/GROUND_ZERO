"""
Live Update Scheduler
---------------------

Central orchestrator that refreshes
all real-time data modules.

Designed for scalable smart-city systems.
"""

import time
import threading

from events.events_collector import collect_all_events
from live_intelligence.crowd_signal_fusion import get_live_crowd
from live_intelligence.tourist_flow_predictor import predict_crowd_next_hours
from external_reviews.review_signal_extractor import extract_review_signals


# refresh intervals (seconds)

EVENTS_INTERVAL = 600
TRAFFIC_INTERVAL = 60
REVIEWS_INTERVAL = 900
PREDICTION_INTERVAL = 120


def events_worker():

    while True:

        try:

            collect_all_events()

        except Exception as e:

            print("events update error", e)

        time.sleep(EVENTS_INTERVAL)


def crowd_worker():

    while True:

        try:

            get_live_crowd()

        except Exception as e:

            print("crowd update error", e)

        time.sleep(TRAFFIC_INTERVAL)


def review_worker():

    while True:

        try:

            extract_review_signals()

        except Exception as e:

            print("review update error", e)

        time.sleep(REVIEWS_INTERVAL)


def prediction_worker():

    while True:

        try:

            predict_crowd_next_hours()

        except Exception as e:

            print("prediction update error", e)

        time.sleep(PREDICTION_INTERVAL)


def start_live_pipeline():

    threads = [

        threading.Thread(target=events_worker),
        threading.Thread(target=crowd_worker),
        threading.Thread(target=review_worker),
        threading.Thread(target=prediction_worker)

    ]

    for t in threads:

        t.daemon = True
        t.start()

    while True:

        time.sleep(1000)


if __name__ == "__main__":

    start_live_pipeline()