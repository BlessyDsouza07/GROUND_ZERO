"""
Live Data Cache
---------------

Stores latest live data snapshots
from all engines.
"""

import threading


class LiveCache:

    def __init__(self):

        self.lock = threading.Lock()

        self.cache = {

            "events": None,
            "crowd": None,
            "reviews": None,
            "predictions": None,
            "sports": None

        }

    def update(self, key, value):

        with self.lock:

            self.cache[key] = value

    def get(self, key):

        with self.lock:

            return self.cache.get(key)


LIVE_CACHE = LiveCache()