import datetime
import pytz

TZ = pytz.timezone('America/New_York')

EQUITY_OPEN = datetime.time(9, 30, 0, tzinfo=TZ)
EQUITY_CLOSE = datetime.time(16, 0, 0, tzinfo=TZ)
EQUITY_EARLY_CLOSE = datetime.time(13, 0, 0, tzinfo=TZ)

# EQUITY_HOLIDAYS and EQUITY_EARLY_HOLIDAYS will need to be updated each year
EQUITY_HOLIDAYS = [
    datetime.datetime(2022, 1, 17, tzinfo=TZ).date(),
    datetime.datetime(2022, 2, 21, tzinfo=TZ).date(),
    datetime.datetime(2022, 4, 15, tzinfo=TZ).date(),
    datetime.datetime(2022, 5, 30, tzinfo=TZ).date(),
    datetime.datetime(2022, 6, 20, tzinfo=TZ).date(),
    datetime.datetime(2022, 7, 4, tzinfo=TZ).date(),
    datetime.datetime(2022, 9, 5, tzinfo=TZ).date(),
    datetime.datetime(2022, 11, 24, tzinfo=TZ).date(),
    datetime.datetime(2022, 12, 26, tzinfo=TZ).date()
]
EQUITY_EARLY_HOLIDAYS = [
    datetime.datetime(2022, 11, 25, tzinfo=TZ).date()
]


class HolidayCalendar():
    def is_market_open(self, product, dt):
        # equity market
        if product.attrs['asset_type'] == 'Equity':
            day, date, time = dt.weekday(), dt.date(), dt.time()
            if date in EQUITY_HOLIDAYS or date in EQUITY_EARLY_HOLIDAYS:
                if date in EQUITY_EARLY_HOLIDAYS and time >= EQUITY_OPEN and time <= EQUITY_EARLY_CLOSE:
                    return True
                return False
            if day < 5 and time >= EQUITY_OPEN and time <= EQUITY_CLOSE:
                return True
            return False
        # all other markets (crypto, fx, metal)
        return True
