from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from pyth_observer.check.publisher import PriceUpdate


@dataclass
class StallDetectionResult:
    """Results from stall detection analysis."""

    is_stalled: bool
    stall_type: Optional[
        str
    ]  # 'exact' for identical values, 'noisy' for artificial noise
    base_price: Optional[float]
    noise_magnitude: Optional[float]
    duration: float  # how long the price has been stalled
    confidence: float

    @classmethod
    def no_stall(cls) -> "StallDetectionResult":
        """Create a StallDetectionResult instance indicating no stall detected."""
        return cls(
            is_stalled=False,
            stall_type=None,
            base_price=None,
            noise_magnitude=None,
            duration=0.0,
            confidence=0.0,
        )


class StallDetector:
    """
    Detects price staleness by identifying both exact price repeats and artificial noise patterns.

    The detection strategy is based on the intuition that meaningful price movements must exceed
    some minimum relative threshold. If a price very slightly fluctuates but doesn't exceed the
    `noise_threshold` within `stall_time_limit`, then it's likely that it's just a static price
    with artificial noise thrown in.

    Detection Logic:
    1. Exact Stalls: Prices within `stall_time_limit` are exactly equal (within float precision)
    2. Noisy Stalls: All price variations stay within a tiny relative `noise_threshold` (default 0.01%)
       for longer than `stall_time_limit`.

    The `noise_threshold` (default 1e-4 or 0.01%) strategy is chosen because:
    - Real price movements, even for very stable symbols, should exceed this threshold.
    - Hard to circumvent. Avoiding detection would require larger variations, impacting the publisher's
      price accuracy versus the aggregate.
    - The threshold is relative to the base price, making it work across different price scales.
    - It works across different noise patterns (random, sine wave, structured, etc.)

    Example:
    - A $100 base price with all variations within ±$0.01 (0.01%) for 2+ minutes is likely stalled
    - Natural price movements would occasionally exceed this tiny threshold
    - Variations this small consistently over time suggest artificial noise
    """

    def __init__(
        self,
        stall_time_limit: float,
        noise_threshold: float = 1e-4,
        min_noise_samples: int = 5,
    ):
        """
        Initialize stall detector.

        Args:
            stall_time_limit: Time in seconds before price is considered stalled
            noise_threshold: Maximum relative noise magnitude (e.g., 1e-4 for 0.01%)
            min_noise_updates: Minimum number of updates needed for noise detection
              (doesn't apply to exact stall detection)
        """
        self.stall_time_limit = stall_time_limit
        self.noise_threshold = noise_threshold
        self.min_noise_samples = min_noise_samples

    def analyze_updates(self, updates: List[PriceUpdate]) -> StallDetectionResult:
        """
        Assumes that the cache has been recently updated since it takes the latest
        cached timestamp as the current time.

        Args:
            updates: List of price updates to analyze

        Returns:
            StallDetectionResult with detection details
        """
        # Need at least 2 samples
        if not updates or len(updates) < 2:
            return StallDetectionResult.no_stall()

        ## Check for exact stall

        # The latest 2 updates are sufficient to detect an exact stall
        latest_updates = updates[-2:]
        duration = latest_updates[1].timestamp - latest_updates[0].timestamp
        if duration <= self.stall_time_limit:
            return StallDetectionResult.no_stall()
        elif latest_updates[1].price == latest_updates[0].price:
            return StallDetectionResult(
                is_stalled=True,
                stall_type="exact",
                base_price=latest_updates[1].price,
                noise_magnitude=0.0,
                duration=duration,
                confidence=1.0,
            )

        ## Check for stalled price with artificial noise added in

        # Calculate relative deviations from base price
        prices = np.array([u.price for u in updates])
        base_price = np.median(prices)

        if base_price == 0:
            # Avoid division by zero
            return StallDetectionResult.no_stall()

        relative_deviations = np.abs(prices - base_price) / abs(base_price)
        max_relative_deviation = np.max(relative_deviations)

        # Check for artificial noise (variations below threshold)
        if len(updates) < self.min_noise_samples:
            # We need multiple samples to detect noise, pass until we have enough
            return StallDetectionResult.no_stall()

        if max_relative_deviation <= self.noise_threshold:
            confidence = 1.0 - (max_relative_deviation / self.noise_threshold)
            return StallDetectionResult(
                is_stalled=True,
                stall_type="noisy",
                base_price=base_price,
                noise_magnitude=max_relative_deviation * base_price,
                duration=duration,
                confidence=confidence,
            )

        return StallDetectionResult(
            is_stalled=False,
            stall_type=None,
            base_price=base_price,
            noise_magnitude=max_relative_deviation * base_price,
            duration=duration,
            confidence=0.0,
        )
