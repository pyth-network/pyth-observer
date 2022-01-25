import os
import datetime
from typing import Tuple, List, Optional

from pythclient.pythaccounts import TwEmaType, PythPriceAccount


# The validators for Prices
price_validators = []

# The vlaidators for Price Accounts
price_account_validators = []


class RegisterValidator(type):
    """
    Register all of the events with metaclass magic.

        https://xkcd.com/353/
    """

    register_to = []  # Just to fake out pyright

    def __new__(cls, name, bases, class_dict):
        cls = type.__new__(cls, name, bases, class_dict)
        if all(
            [
                hasattr(cls, "register_to"),
                cls.__name__
                not in ("PriceValidationEvent", "PriceAccountValidationEvent"),
            ]
        ):
            cls.register_to.append(cls)
        return cls


class ValidationEvent:
    error_code: str = "validation-event"

    def __init__(
        self,
        publisher_key: Optional[str] = None,
        price=None,
        price_account=None,
        network=None,
        symbol=None,
    ) -> None:
        self.price = price
        self.symbol = symbol
        self.network = network
        self.price_account = price_account
        self.publisher_key = publisher_key
        self.creation_time = datetime.datetime.now()

        if publisher_key:
            # PythPriceComponent's latest_price_info
            self.publisher_latest = self.price.quoters[self.publisher_key]
            # Actual publisher name or public key
            self.publisher_name = self.price.publisher_name(self.publisher_key)
            # PythPriceComponent's last_aggregate_price_info
            self.publisher_aggregate = self.price.quoter_aggregates[self.publisher_key]

    def get_event_details(self) -> Tuple[str, List[str]]:
        return "", []

    def is_valid(self) -> bool:
        raise NotImplementedError

    def is_noisy(self) -> bool:
        return False

    @property
    def unique_id(self) -> str:
        """
        Get a per-event unique id
        """
        if self.publisher_key is None:
            # e.g.: negative-twap-SHIB/USD
            return f"{self.error_code}-{self.symbol}"
        # e.g.: pubname-bad-confidence-BTC/USD
        return f"{self.publisher_name}-{self.error_code}-{self.symbol}"


class PriceValidationEvent(ValidationEvent, metaclass=RegisterValidator):
    """
    These validators run over every single price component
    """

    register_to = price_validators


class PriceAccountValidationEvent(ValidationEvent, metaclass=RegisterValidator):
    """
    These validators run over every price account
    """

    register_to = price_account_validators

    def convert_raw(self, num, exponent):
        """
        For converting raw_* to the more human friendly versions
        """
        return num * (10 ** exponent)


class BadConfidence(PriceValidationEvent):
    """
    When the confidence interval is less than or equal to zero and the
    status is Trading.
    """

    error_code: str = "bad-confidence"

    def is_valid(self):
        if self.publisher_aggregate.confidence_interval <= 0:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:

        title = f"{self.publisher_name.upper()} bad confidence for {self.symbol}"

        details = [
            f"Confidence: {self.publisher_aggregate.confidence_interval:.2f}",
            f"Status: {self.publisher_aggregate.price_status.name}",
        ]
        return title, details


class ImprobableAggregate(PriceValidationEvent):
    """
    Improbable aggregate: 's price/confidence interval are
    such that an aggregate price is more than 20 confidence intervals
    away.

    This error is due to a price that is far from the aggregate, or a
    confidence interval that is too small. This can be very noisy due
    to many publishers with small confidence intervals.
    """

    threshold: int = 20
    error_code: str = "improbable-aggregate"

    def is_valid(self) -> bool:
        delta = self.publisher_aggregate.price - self.price.aggregate.price

        # The normalized confidence
        self.confidence = abs(delta / self.publisher_aggregate.confidence_interval)

        if (self.price.is_publishing(self.publisher_key) and
                self.price.is_aggregate_publishing() and
                self.confidence > self.threshold):
            return False
        return True

    def is_noisy(self) -> bool:
        """
        This event can be very noisy due to publishers using a very
        small confidence interval
        """
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg = self.price.aggregate
        published = self.publisher_aggregate

        title = (
            f"{self.publisher_name.upper()} is {self.confidence:.2f} "
            f"confidence intervals away on {self.symbol}"
        )
        details = [
            f"Aggregate: {agg.price:.2f} ± {agg.confidence_interval:.2f} (slot {agg.slot})",
            f"Published:  {published.price:.2f} ± {published.confidence_interval:.2f} (slot {published.slot})",
        ]
        return title, details


class PriceDeviation(PriceValidationEvent):
    """
    Published price is too far away from the aggregate price.
    """

    threshold: int = int(os.environ.get("PYTH_OBSERVER_PRICE_DEVIATION_THRESHOLD", 6))
    error_code: str = "price-deviation"

    def is_valid(self) -> bool:
        delta = self.publisher_aggregate.price - self.price.aggregate.price
        self.deviation = abs(delta / self.price.aggregate.price) * 100

        if (self.price.is_publishing(self.publisher_key) and
                self.price.is_aggregate_publishing() and
                self.deviation > self.threshold):
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg = self.price.aggregate
        published = self.publisher_aggregate

        title = f"{self.publisher_name.upper()} price is {self.deviation:.0f}% off on {self.symbol}"
        details = [
            f"Aggregate: {agg.price:.2f} (slot {agg.slot})",
            f"Published:  {published.price:.2f} (slot {published.slot})",
        ]
        return title, details


class StoppedPublishing(PriceValidationEvent):
    """
    When a price has stopped being published for at least 600 slots but
    less than 1000 slots.
    """
    error_code: str = "stop-publishing-about-5-mins"
    threshold_min = int(os.environ.get("PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS", 600))
    threshold_max = int(os.environ.get("PYTH_OBSERVER_STOP_PUBLISHING_MAX_SLOTS", 1000))

    def is_valid(self) -> bool:
        aggregate = self.price.aggregate.slot
        published = self.publisher_latest.slot

        # >= 600 && < 1000 is bad
        self.stopped_slots = aggregate - published

        if self.stopped_slots >= self.threshold_min and self.stopped_slots < self.threshold_max:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"{self.publisher_name.upper()} stopped publishing {self.symbol} for {self.stopped_slots} slots"
        details = (
            f"Aggregate last slot: {self.price.aggregate.slot}"
            f"Published last slot: {self.publisher_latest.slot}"
        )


# Price Account events


class NegativeTWAP(PriceAccountValidationEvent):
    error_code: str = "negative-twap"

    def is_valid(self) -> bool:
        self.twap = self.convert_raw(
            self.price_account.derivations[TwEmaType.TWAPVALUE],
            self.price_account.exponent,
        )
        return self.twap >= 0

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = f"{self.symbol} negative TWAP"
        details = [
            f"TWAP: {self.twap:.2f} (slot self{self.price_account.slot})",
            f"Aggregate: {agg_price:.2f} (slot {self.price_account.aggregate_price_info.slot})",
        ]
        return title, details


class NegativeTWAC(PriceAccountValidationEvent):
    error_code: str = "negative-twac"

    def is_valid(self) -> bool:
        self.twac = self.convert_raw(
            self.price_account.derivations[TwEmaType.TWACVALUE],
            self.price_account.exponent,
        )
        return self.twac >= 0

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = f"{self.symbol} negative TWAC"
        details = [
            f"TWAC: {self.twac:.2f} (slot {self.price_account.slot})",
            f"Aggregate: {agg_price:.2f} (slot {self.price_account.aggregate_price_info.slot})",
        ]
        return title, details


class TWAPvsAggregate(PriceAccountValidationEvent):
    """
    When the TWAP and Aggregate are significantly off, it is due to
    something wonky or big price moves.
    """
    error_code: str = "twap-vs-aggregate-price"
    threshold = int(os.environ.get('PYTH_OBSERVER_TWAP_VS_AGGREGATE_THRESHOLD', 10))

    def is_valid(self) -> bool:
        self.twap = self.convert_raw(
            num=self.price_account.derivations[TwEmaType.TWAPVALUE],
            exponent=self.price_account.exponent,
        )
        aggregate_price = self.price_account.aggregate_price

        try:
            self.deviation = 100 * abs(self.twap - aggregate_price) / aggregate_price
        # When a publisher publishes garbage data this has happened before
        except ZeroDivisionError as exc:
            return True

        if self.deviation > self.threshold:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = f"{self.symbol} Aggregate is {self.deviation:.0f}% different than TWAP"
        details = [
            f"TWAP: {self.twap:.2f} (slot {self.price_account.slot})",
            f"Aggregate: {agg_price:.3f} (slot {self.price_account.aggregate_price_info.slot})",
        ]
        return title, details
