import asyncio

from asyncio_throttle import Throttler
from loguru import logger
from pythclient.pythclient import PythClient, PythPriceAccount

from pyth_observer.coingecko import get_coingecko_prices
from pyth_observer.prices import PriceValidator


class PriceAccountObserver:
  def __init__(self, client: PythClient, throttler: Throttler, price_account: PythPriceAccount):
    self.client = client
    self.throttler = throttler
    self.price_account = price_account

  async def run(self) -> None:
    while True:
      logger.debug(f"Observing: {self.price_account.product.symbol}")

      coingecko_price = await get_coingecko_prices(self.price_account.product.attrs["base"])

      events = PriceValidator(
          symbol=self.price_account.product.symbol,
          coingecko_price=coingecko_price.get(self.price_account.product.attrs["base"]),
      ).verify_price_account(self.price_account)

      if events:
        logger.warning(events)

      await asyncio.sleep(30)
