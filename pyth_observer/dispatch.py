from typing import Any, Dict, List, Union

from loguru import logger

from pyth_observer.checks.price_feed import (
    PriceFeedCheck,
    PriceFeedCoinGeckoCheck,
    PriceFeedCrossChainDeviationCheck,
    PriceFeedCrossChainOnlineCheck,
    PriceFeedOnlineCheck,
    PriceFeedState,
)
from pyth_observer.checks.publisher import (
    PublisherAggregateCheck,
    PublisherCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
    PublisherState,
)

PRICE_FEED_CHECKS = [
    PriceFeedCoinGeckoCheck,
    PriceFeedCrossChainDeviationCheck,
    PriceFeedCrossChainOnlineCheck,
    PriceFeedOnlineCheck,
]

PUBLISHER_CHECKS = [
    PublisherAggregateCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
]


class Dispatch:
    """
    Load configuration for each check/state pair, run the check, and run
    notifiers for the checks that failed.
    """

    def __init__(self, config, publishers):
        self.config = config
        self.publishers = publishers

    def run(self, states: List[Union[PriceFeedState, PublisherState]]):
        failed_checks: List[Union[PriceFeedCheck, PublisherCheck]] = []

        for state in states:
            if isinstance(state, PriceFeedState):
                failed_checks.extend(self.check_price_feed(state))
            elif isinstance(state, PublisherState):
                failed_checks.extend(self.check_publisher(state))
            else:
                raise RuntimeError("Unknown state")

        # TODO: Dispatch failed checks to notifiers
        for check in failed_checks:
            if isinstance(check, PriceFeedCheck):
                logger.warning(check.log_entry())
            elif isinstance(check, PublisherCheck):
                logger.warning(check.log_entry(self.publishers))
            else:
                raise RuntimeError("Unknown check")

    def check_price_feed(self, state: PriceFeedState) -> List[PriceFeedCheck]:
        failed_checks: List[PriceFeedCheck] = []

        for check_class in PRICE_FEED_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)
            check = check_class(state, config)

            if config["enable"] and not check.run():
                failed_checks.append(check)

        return failed_checks

    def check_publisher(self, state) -> List[PublisherCheck]:
        failed_checks: List[PublisherCheck] = []

        for check_class in PUBLISHER_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)
            check = check_class(state, config)

            if config["enable"] and not check.run():
                failed_checks.append(check)

        return failed_checks

    def load_config(self, check_name: str, symbol: str) -> Dict[str, Any]:
        config = self.config["checks"]["global"][check_name]

        if symbol in self.config["checks"]:
            if check_name in self.config["checks"][symbol]:
                config |= self.config["checks"][symbol][check_name]

        return config
