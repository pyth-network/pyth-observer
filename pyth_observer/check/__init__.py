from pyth_observer.check.price_feed import (
    PriceFeedCheck,
    PriceFeedCheckConfig,
    PriceFeedState,
)
from pyth_observer.check.publisher import (
    PublisherCheck,
    PublisherCheckConfig,
    PublisherState,
)

Check = PriceFeedCheck | PublisherCheck
State = PriceFeedState | PublisherState
Config = PriceFeedCheckConfig | PublisherCheckConfig
