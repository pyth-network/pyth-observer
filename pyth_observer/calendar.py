import datetime

EQUITY_START = datetime.time(9, 30, 0)
EQUITY_CLOSE = datetime.time(16, 0, 0)
EQUITY_EARLY_CLOSE = datetime.time(13, 0, 0)
EQUITY_HOLIDAYS = ["2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30",
                   "2022-06-20", "2022-07-04", "2022-09-05", "2022-11-24", "2022-11-25", "2022-12-26"]
EQUITY_HOLIDAYS_EARLY = ["2022-11-25"]
EQUITY_TRADING_DAYS = [1, 2, 3, 4, 5]

FX_START = datetime.time(17, 0, 0)
FX_CLOSE = datetime.time(16, 0, 0)
FX_TRADING_DAYS = [7, 1, 2, 3, 4, 5]

METAL_START = datetime.time(18, 3, 0)
METAL_CLOSE = datetime.time(16, 58, 0)
METAL_TRADING_DAYS = [7, 1, 2, 3, 4, 5]


class Calendar:
    def is_market_open(self, product, dt):
        day, date, time = dt.weekday(), dt.date(), dt.time()
        if product.attrs["asset_type"] == "Equity":
            # market holiday
            if date.strftime("%Y-%m-%d") in EQUITY_HOLIDAYS:
                # market within early closing hours
                if date.strftime("%Y-%m-%d") in EQUITY_HOLIDAYS_EARLY and time >= EQUITY_START and time <= EQUITY_EARLY_CLOSE:
                    breakpoint()
                    return True
                # market after holiday closing hours
                return False
            # market within regular opening hours
            if day in EQUITY_TRADING_DAYS and time >= EQUITY_START and time <= EQUITY_CLOSE:
                return True
            # market closed
            return False
        elif product.attrs["asset_type"] == "FX":
            if day in FX_TRADING_DAYS:
                if (day == 7 and time < FX_START) or (day == 5 and time > FX_CLOSE):
                    return False
                return True
            return False
        elif product.attrs["asset_type"] == "Metal":
            pass
        else:  # Crypto
            return True
