import datetime

import pytz

TZ = pytz.timezone("America/New_York")

EQUITY_OPEN = datetime.time(9, 30, 0, tzinfo=TZ)
EQUITY_CLOSE = datetime.time(16, 0, 0, tzinfo=TZ)
EQUITY_EARLY_CLOSE = datetime.time(13, 0, 0, tzinfo=TZ)

# EQUITY_HOLIDAYS and EQUITY_EARLY_HOLIDAYS will need to be updated each year
# From https://www.nyse.com/markets/hours-calendars
EQUITY_HOLIDAYS = [
    datetime.datetime(2023, 1, 2, tzinfo=TZ).date(),
    datetime.datetime(2023, 1, 16, tzinfo=TZ).date(),
    datetime.datetime(2023, 2, 20, tzinfo=TZ).date(),
    datetime.datetime(2023, 4, 7, tzinfo=TZ).date(),
    datetime.datetime(2023, 5, 29, tzinfo=TZ).date(),
    datetime.datetime(2023, 6, 19, tzinfo=TZ).date(),
    datetime.datetime(2023, 7, 4, tzinfo=TZ).date(),
    datetime.datetime(2022, 9, 4, tzinfo=TZ).date(),
    datetime.datetime(2023, 11, 23, tzinfo=TZ).date(),
    datetime.datetime(2023, 12, 25, tzinfo=TZ).date(),
]

EQUITY_EARLY_HOLIDAYS = [
    datetime.datetime(2023, 7, 3, tzinfo=TZ).date(),
    datetime.datetime(2023, 11, 24, tzinfo=TZ).date(),
]

FX_METAL_CLOSE_TIME = datetime.time(17, 0, 0, tzinfo=TZ)
FX_METAL_OPEN_TIME = datetime.time(12, 0, 0, tzinfo=TZ)


class HolidayCalendar:
    def is_market_open(self, asset_type: str, dt: datetime.datetime):
        day, date, time = dt.weekday(), dt.date(), dt.time()

        if asset_type == "Equity":
            if date in EQUITY_HOLIDAYS or date in EQUITY_EARLY_HOLIDAYS:
                if (
                    date in EQUITY_EARLY_HOLIDAYS
                    and time >= EQUITY_OPEN
                    and time <= EQUITY_EARLY_CLOSE
                ):
                    return True
                return False
            if day < 5 and time >= EQUITY_OPEN and time <= EQUITY_CLOSE:
                return True
            return False

        if asset_type in ["FX", "Metal"]:
            # The market for FX and Metal is closed from Friday 5pm to Sunday 5pm

            # Friday the market is close after 5pm
            if day == 4 and time > FX_METAL_CLOSE_TIME:
                return False
            # Saturday the market is closed all the time
            if day == 5:
                return False
            # Sunday the market is closed before 5pm
            if day == 6 and time < FX_METAL_OPEN_TIME:
                return False

            return True

        # all other markets (crypto)
        return True
