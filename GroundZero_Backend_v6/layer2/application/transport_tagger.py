"""
Transport tagging (blueprint 5.5). Estimates mode, duration, and cost
between consecutive slots using haversine distance — real geometry, not a
flat guess per hop.

Fare constants are calibrated against real Mangaluru rates, not invented:
  - Auto rickshaw: official Dakshina Kannada RTA tariff — Rs 35 minimum
    fare covering the first 1.5 km, then Rs 20 for every additional km
    (revised rate effective December 2025, reported by Daijiworld:
    https://daijiworld.com/news/newsDisplay?newsID=1023026). Modeled as a
    genuine two-tier fare (flat up to 1.5km, then per-km), not a flat
    per-km rate from zero, to match how the meter actually works.
  - Cab: no single official local-ride tariff card was found (outstation
    per-km rates exist but don't apply to short in-city hops); using a
    representative sedan local rate of ~Rs 13/km with an ~Rs 80 base fare,
    within the commonly reported Rs 12-15/km range for hatchback/sedan
    local rides in Mangalore. This constant is more approximate than the
    auto rate above and worth re-checking against a live ride-hailing
    quote if precision matters later.
"""
from __future__ import annotations

from layer0.application.dedup import haversine_meters
from layer0.domain.entities import Place
from layer2.domain.entities import TransportEstimate, TransportMode

WALK_MAX_METERS = 800
AUTO_MAX_METERS = 6000

WALK_SPEED_M_PER_MIN = 80
AUTO_SPEED_M_PER_MIN = 250
CAB_SPEED_M_PER_MIN = 350

# Auto: official RTA two-tier tariff (see module docstring).
AUTO_MINIMUM_FARE_INR = 35
AUTO_MINIMUM_FARE_KM = 1.5
AUTO_PER_KM_AFTER_MINIMUM_INR = 20

# Cab: representative local sedan rate (see module docstring).
CAB_BASE_FARE_INR = 80
CAB_PER_KM_INR = 13


class TransportTagger:
    def estimate(self, origin: Place, destination: Place) -> TransportEstimate:
        coords = (
            origin.coordinates.latitude, origin.coordinates.longitude,
            destination.coordinates.latitude, destination.coordinates.longitude,
        )
        if any(c is None for c in coords):
            # Missing coordinates (e.g. a community-submitted place with no
            # lat/lon on record) — fall back to a conservative cab estimate
            # rather than crashing the whole recommendation queue.
            return TransportEstimate(mode=TransportMode.CAB, duration_minutes=15, cost_inr=150.0)
        distance_m = haversine_meters(*coords)

        if distance_m <= WALK_MAX_METERS:
            duration = max(1, round(distance_m / WALK_SPEED_M_PER_MIN))
            return TransportEstimate(mode=TransportMode.WALK, duration_minutes=duration, cost_inr=0.0)

        if distance_m <= AUTO_MAX_METERS:
            duration = max(1, round(distance_m / AUTO_SPEED_M_PER_MIN))
            distance_km = distance_m / 1000
            if distance_km <= AUTO_MINIMUM_FARE_KM:
                cost = float(AUTO_MINIMUM_FARE_INR)
            else:
                cost = AUTO_MINIMUM_FARE_INR + (distance_km - AUTO_MINIMUM_FARE_KM) * AUTO_PER_KM_AFTER_MINIMUM_INR
            return TransportEstimate(mode=TransportMode.AUTO, duration_minutes=duration, cost_inr=round(cost, 2))

        duration = max(1, round(distance_m / CAB_SPEED_M_PER_MIN))
        cost = round(CAB_BASE_FARE_INR + (distance_m / 1000) * CAB_PER_KM_INR, 2)
        return TransportEstimate(mode=TransportMode.CAB, duration_minutes=duration, cost_inr=cost)