
class PublisherPriceObserver:
  def __init__(self, client: PythClient, throttler: Throttler, price_account: PythPriceAccount):
    self.client = client
    self.throttler = throttler
    self.price_account = price_account

  async def run(self) -> None:
    while True:
      continue