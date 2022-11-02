from abc import abstractmethod
from typing import Protocol, Union, Dict, Any

from pyth_observer.checks.price_feed import PriceFeedState
from pyth_observer.checks.publisher import PublisherState

Config = Dict[str, Union[str, float, int, bool]]

State = Union[PriceFeedState, PublisherState]


class Check(Protocol):
    state: State

    def __init__(self, state: State, config: Config):
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> str:
        ...
