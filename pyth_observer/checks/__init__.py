from pyth_observer.checks.price_feed import (
    PriceFeedState,
    PriceFeedCheck,
    PriceFeedCheckConfig,
)
from pyth_observer.checks.publisher import (
    PublisherState,
    PublisherCheck,
    PublisherCheckConfig,
)

Check = PriceFeedCheck | PublisherCheck
State = PriceFeedState | PublisherState
Config = PriceFeedCheckConfig | PublisherCheckConfig
