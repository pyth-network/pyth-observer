import os
import time
import datetime
import pytz
from typing import Tuple, List, Optional

from pythclient.pythaccounts import EmaType, PythPriceStatus

from pyth_observer.calendar import HolidayCalendar
from pyth_observer.coingecko import get_coingecko_market_id


# The validators for Prices
price_validators = []

# The validators for Price Accounts
price_account_validators = []

calendar = HolidayCalendar()

MAX_SLOT_DIFFERENCE = 25
TZ = pytz.timezone("America/New_York")


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
        coingecko_price=None,
        coingecko_price_last_updated_at=None,
        crosschain_price=None,
    ) -> None:
        self.price = price
        self.symbol = symbol
        self.network = network
        self.price_account = price_account
        self.publisher_key = publisher_key
        self.coingecko_price = coingecko_price
        self.coingecko_price_last_updated_at = coingecko_price_last_updated_at
        self.crosschain_price = crosschain_price
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
        """
        Return True if the invariant checked by this event is satisfied.
        Return False if the event should trigger a notification.
        """
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
        return num * (10**exponent)


class BadConfidence(PriceValidationEvent):
    """
    When the confidence interval is less than or equal to zero and the
    status is Trading.
    """

    error_code: str = "bad-confidence"

    def is_valid(self):
        neg_ci = self.publisher_aggregate.confidence_interval <= 0
        trading = self.publisher_aggregate.price_status == PythPriceStatus.TRADING
        if neg_ci and trading:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:

        title = f"{self.publisher_name.upper()} bad confidence for {self.symbol}"

        details = [
            f"Confidence: {self.publisher_aggregate.confidence_interval:.3f}",
            f"Status: {self.publisher_aggregate.price_status.name}",
        ]
        return title, details

    def is_noisy(self) -> bool:
        """
        This event can be very noisy due to publishers using less than or equal to zero confidence interval
        """
        return True


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

        if self.publisher_aggregate.confidence_interval != 0:
            # The normalized confidence
            self.confidence = abs(delta / self.publisher_aggregate.confidence_interval)

            if (
                self.price.is_publishing(self.publisher_key)
                and self.price.is_aggregate_publishing()
                and self.confidence > self.threshold
            ):
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
            f"Aggregate: {agg.price:.3f} ± {agg.confidence_interval:.3f} (slot {agg.pub_slot})",
            f"Published:  {published.price:.3f} ± {published.confidence_interval:.3f} (slot {published.pub_slot})",
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
        if self.price.aggregate.price == 0:
            # TODO: add another alert that validates whether the aggregate price is close to the truth
            return True

        self.deviation = abs(delta / self.price.aggregate.price) * 100

        if (
            self.price.is_publishing(self.publisher_key)
            and self.price.is_aggregate_publishing()
            and self.deviation > self.threshold
        ):
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg = self.price.aggregate
        published = self.publisher_aggregate
        title = f"{self.publisher_name.upper()} price is {self.deviation:.0f}% off on {self.symbol}"
        details = [
            f"Aggregate: {agg.price:.3f} ± {agg.confidence_interval:.3f} (slot {agg.pub_slot})",
            f"Published:  {published.price:.3f} ± {published.confidence_interval:.3f} (slot {published.pub_slot})",
        ]
        return title, details


class StoppedPublishing(PriceValidationEvent):
    """
    When a price has stopped being published for at least 600 slots but
    less than 1000 slots.
    """

    error_code: str = "stopped-publishing-about-5-mins"
    threshold_min = int(os.environ.get("PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS", 600))
    threshold_max = int(os.environ.get("PYTH_OBSERVER_STOP_PUBLISHING_MAX_SLOTS", 1000))

    def is_valid(self) -> bool:
        aggregate = self.price.aggregate.pub_slot
        published = self.publisher_latest.pub_slot

        # >= 600 && < 1000 is bad
        self.stopped_slots = aggregate - published

        if (
            self.stopped_slots >= self.threshold_min
            and self.stopped_slots < self.threshold_max
        ):
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"{self.publisher_name.upper()} stopped publishing {self.symbol} for {self.stopped_slots} slots"
        details = [
            f"Aggregate last slot: {self.price.aggregate.pub_slot}",
            f"Published last slot: {self.publisher_latest.pub_slot}",
        ]
        return title, details


class PublisherPriceFeedOffline(PriceValidationEvent):
    """
    This alert is supposed to fire when a publisher price feed should be
    updating, but isn't. It alerts when a publisher price hasn't updated its
    price in > 25 slots OR its status is unknown.
    """

    error_code: str = "publisher-price-feed-offline"

    def is_valid(self) -> bool:
        self.slot_diff = self.price.slot - self.publisher_latest.pub_slot

        if (
            self.slot_diff > MAX_SLOT_DIFFERENCE
            or self.publisher_latest.price_status != PythPriceStatus.TRADING
        ):
            market_open = calendar.is_market_open(
                self.price.product_attrs["asset_type"], datetime.datetime.now(tz=TZ)
            )
            if market_open:
                return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"{self.publisher_key} {self.symbol} price feed is offline "
        title += "(has not updated its price in > 25 slots OR status is unknown)"
        details = [
            f"Last Updated Slot: {self.publisher_latest.pub_slot}",
            f"Current Slot: {self.price.slot}",
            f"Status: {self.publisher_latest.price_status}",
        ]
        return title, details

    def is_noisy(self) -> bool:
        """
        This event can be very noisy due to publishers going offline on each price feeds
        """
        return True


# Price Account events


class PriceFeedOffline(PriceAccountValidationEvent):
    """
    This alert is supposed to fire when a price feed should be updating, but
    isn't. It alerts when a price hasn't updated its price in > 25 slots OR
    its status is unknown.
    """

    error_code: str = "price-feed-offline"

    def is_valid(self) -> bool:
        self.slot_diff = (
            self.price_account.slot - self.price_account.aggregate_price_info.pub_slot
        )
        trading = (
            self.price_account.aggregate_price_info.price_status
            == PythPriceStatus.TRADING
        )

        if self.slot_diff > MAX_SLOT_DIFFERENCE or not trading:
            market_open = calendar.is_market_open(
                self.price_account.product.attrs["asset_type"],
                datetime.datetime.now(tz=TZ),
            )
            if market_open:
                return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"{self.symbol} price feed is offline (has not updated its"
        title += " price in > 25 slots OR status is unknown)"
        details = [
            f"Last Updated Slot: {self.price_account.aggregate_price_info.pub_slot}",
            f"Current Slot: {self.price_account.slot}",
            f"Status: {self.price_account.aggregate_price_info.price_status}",
        ]
        return title, details

    def is_noisy(self) -> bool:
        """
        This event can be very noisy because several of our price feeds are flaky.
        """
        return True


class LongDurationPriceFeedOffline(PriceAccountValidationEvent):
    """
    This alert fires when a price feed should be updating, but isn't.
    It alerts when a price hasn't updated in > PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS (default 600) slots.
    This alert requires a longer offline duration than PriceFeedOffline.
    """

    error_code: str = "long-price-feed-offline"
    threshold_slots: int = int(
        os.environ.get("PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS", 600)
    )

    def is_valid(self) -> bool:
        # The aggregate's slot field updates even when the status=UNKNOWN, but each publisher's slot
        # only updates when they are included in the aggregate. Therefore, look at the last publish slot
        # for each publisher to determine the last slot in which a sufficient number of publishers were active.
        # This check has perfect precision but imperfect recall.  If the alert fires, the price feed has
        # definitely been offline for the configured duration. However, there are cases when it should fire but
        # doesn't. For example, it will not fire if there are 3 publishers publishing
        # every 100 slots, but spaced so that the 3 are never active at the same time.
        # However, this situation is unlikely.
        active_publishers = self._get_num_active_publishers()
        min_publishers = self.price_account.min_publishers

        # min_publishers >= 10 means the feed is "coming soon". We expect it to be offline.
        if (
            active_publishers < self.price_account.min_publishers
            and min_publishers < 10
        ):
            market_open = calendar.is_market_open(
                self.price_account.product.attrs["asset_type"],
                datetime.datetime.now(tz=TZ),
            )
            if market_open:
                return False
        return True

    def _get_num_active_publishers(self) -> int:
        active_publishers = 0
        for component in self.price_account.price_components:
            stopped_slots = (
                self.price_account.last_slot
                - component.last_aggregate_price_info.pub_slot
            )
            if stopped_slots < self.threshold_slots:
                active_publishers += 1

        return active_publishers

    def get_event_details(self) -> Tuple[str, List[str]]:
        # There's not a good way to get the last time the feed updated, unfortunately.
        title = f"{self.symbol} price feed is offline (no update for > {self.threshold_slots} slots)"
        details = [
            f"Current Slot: {self.price_account.slot}",
            f"Status: {self.price_account.aggregate_price_info.price_status}",
        ]
        return title, details


class NegativeTWAP(PriceAccountValidationEvent):
    error_code: str = "negative-twap"

    def is_valid(self) -> bool:
        self.twap = self.convert_raw(
            self.price_account.derivations[EmaType.EMA_PRICE_VALUE],
            self.price_account.exponent,
        )
        return self.twap >= 0

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = f"{self.symbol} negative TWAP"
        details = [
            f"TWAP: {self.twap:.3f} (slot {self.price_account.slot})",
            f"Aggregate: {agg_price:.3f} (slot {self.price_account.aggregate_price_info.pub_slot})",
        ]
        return title, details


class NegativeTWAC(PriceAccountValidationEvent):
    error_code: str = "negative-twac"

    def is_valid(self) -> bool:
        self.twac = self.convert_raw(
            self.price_account.derivations[EmaType.EMA_CONFIDENCE_VALUE],
            self.price_account.exponent,
        )
        return self.twac >= 0

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = f"{self.symbol} negative TWAC"
        details = [
            f"TWAC: {self.twac:.3f} (slot {self.price_account.slot})",
            f"Aggregate: {agg_price:.3f} (slot {self.price_account.aggregate_price_info.pub_slot})",
        ]
        return title, details


class TWAPvsAggregate(PriceAccountValidationEvent):
    """
    When the TWAP and Aggregate are significantly off, it is due to
    something wonky or big price moves.
    """

    error_code: str = "twap-vs-aggregate-price"
    threshold = int(os.environ.get("PYTH_OBSERVER_TWAP_VS_AGGREGATE_THRESHOLD", 10))

    def is_valid(self) -> bool:
        self.twap = self.convert_raw(
            num=self.price_account.derivations[EmaType.EMA_PRICE_VALUE],
            exponent=self.price_account.exponent,
        )
        aggregate_price = self.price_account.aggregate_price

        # aggregate price is not currently available
        if not aggregate_price:
            return True

        try:
            self.deviation = 100 * abs(self.twap - aggregate_price) / aggregate_price
        # When a publisher publishes garbage data this has happened before
        except ZeroDivisionError:
            return True

        if self.deviation > self.threshold:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        agg_price = self.price_account.aggregate_price

        title = (
            f"{self.symbol} Aggregate is {self.deviation:.0f}% different than EMA Price"
        )
        details = [
            f"TWAP: {self.twap:.3f} (slot {self.price_account.slot})",
            f"Aggregate: {agg_price:.3f} (slot {self.price_account.aggregate_price_info.pub_slot})",
        ]
        return title, details


class PriceDeviationCoinGecko(PriceAccountValidationEvent):
    """
    This alert fires when a price feed deviates from CoinGecko price feed by a specified threshold.
    """

    error_code: str = "price-deviation-coingecko"
    threshold = int(os.environ.get("PYTH_OBSERVER_PRICE_DEVIATION_COINGECKO", 5))

    def is_valid(self) -> bool:
        # check if coingecko price exists or
        # if it's the first time we're checking this price feed against coingecko
        if not self.coingecko_price or not self.coingecko_price_last_updated_at:
            return True

        # check if coingecko price is stale, we don't want to alert on stale prices
        if (
            self.coingecko_price["last_updated_at"]
            <= self.coingecko_price_last_updated_at
        ):
            return True

        trading = (
            self.price_account.aggregate_price_info.price_status
            == PythPriceStatus.TRADING
        )
        pyth_price = self.price_account.aggregate_price_info.price

        if not trading or pyth_price == 0:
            # TODO: add another alert that checks if coingecko is down
            return True

        self.coingecko_deviation = (
            abs(pyth_price - self.coingecko_price["usd"]) / self.coingecko_price["usd"]
        ) * 100.0

        # Pyth price is more than a specified threshold percentage off CoinGecko's price
        if self.coingecko_deviation > self.threshold:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"{self.symbol} is more than {self.threshold}% off from CoinGecko"
        coin_name = get_coingecko_market_id(self.price_account.product.attrs["base"])
        url = f"https://www.coingecko.com/en/coins/{coin_name}"
        last_updated_at = self.coingecko_price["last_updated_at"]
        details = [
            f"Pyth Price: {self.price_account.aggregate_price_info.price}",
            f"CoinGecko Price: {self.coingecko_price['usd']}",
            f"CoinGecko Price Last Updated At: {last_updated_at}",
            f"Deviation: {self.coingecko_deviation}% off",
            f"CoinGecko Price Chart: {url}",
        ]
        return title, details


class PriceStoppedUpdatingCrosschain(PriceAccountValidationEvent):
    """
    This alert fires when a cross-chain price feed stopped updating
    for the past 1 hour.
    """

    error_code: str = "price-stopped-updating-cross-chain"
    threshold = 3600  # 3600 seconds = 1 hour

    def is_valid(self) -> bool:
        # check if cross-chain price exists
        if not self.crosschain_price:
            return True

        last_updated_difference = (
            int(time.time()) - self.crosschain_price["publish_time"]
        )

        if last_updated_difference > self.threshold:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = f"Cross-chain {self.symbol} stopped updating for more than an hour"
        details = [
            f"Cross-chain price: {self.crosschain_price['price']:.4f}, conf: {self.crosschain_price['conf']:.4f}",
            f"Solana price: {self.price_account.aggregate_price_info.price:.4f},"
            + f" conf: {self.price_account.aggregate_price_info.confidence_interval:.4f}",
            f"Last updated: {self.crosschain_price['publish_time']:.4f}",
        ]
        return title, details

    def is_noisy(self) -> bool:
        """
        This event can be very noisy due to low frequency price updates.
        """
        return True


class PriceDeviationCrosschain(PriceAccountValidationEvent):
    """
    This alert fires when a cross-chain price feed deviates
    from Solana price feed by a specified threshold.
    """

    error_code: str = "price-deviation-cross-chain"
    threshold = int(os.environ.get("PYTH_OBSERVER_PRICE_DEVIATION_CROSSCHAIN", 5))

    def is_valid(self) -> bool:
        # check if cross-chain price exists
        if not self.crosschain_price:
            return True

        trading = (
            self.price_account.aggregate_price_info.price_status
            == PythPriceStatus.TRADING
        )
        pyth_price = self.price_account.aggregate_price_info.price

        if not trading or pyth_price == 0:
            return True

        self.crosschain_deviation = (
            abs(self.crosschain_price["price"] - pyth_price) / pyth_price
        ) * 100.0

        # check for stale prices
        if int(time.time()) - self.crosschain_price["publish_time"]:
            return True

        if self.crosschain_deviation > self.threshold:
            return False
        return True

    def get_event_details(self) -> Tuple[str, List[str]]:
        title = (
            f"Cross-chain {self.symbol} is more than {self.threshold}%"
            + f" off from Solana {self.symbol}"
        )
        details = [
            f"Cross-chain price: {self.crosschain_price['price']:.4f}, conf: {self.crosschain_price['conf']:.4f}",
            f"Solana price: {self.price_account.aggregate_price_info.price:.4f},"
            + f" conf: {self.price_account.aggregate_price_info.confidence_interval:.4f}",
            f"Deviation: {self.crosschain_deviation}% off",
        ]
        return title, details
