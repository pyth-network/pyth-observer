import datetime

EQUITY_OPEN = datetime.time(9, 30, 0)
EQUITY_CLOSE = datetime.time(16, 0, 0)
EQUITY_EARLY_CLOSE = datetime.time(13, 0, 0)
EQUITY_HOLIDAYS = ["17-01-2022", "08-02-2022", "21-02-2022", "15-04-2022", "30-05-2022",
                   "20-06-2022", "04-07-2022", "05-09-2022", "24-11-2022", "25-11-2022", "26-12-2022"]
EQUITY_EARLY_HOLIDAYS = ["08-02-2022", "25-11-2022"]


class Calendar():
    def is_market_open(self, product, dt):
        # equity market
        if product.attrs['asset_type'] == 'Equity':
            day, date, time = dt.weekday(), dt.date(), dt.time()
            date_str = date.strftime("%d-%m-%Y")
            if date_str in EQUITY_HOLIDAYS:
                if date_str in EQUITY_EARLY_HOLIDAYS and time >= EQUITY_OPEN and time <= EQUITY_EARLY_CLOSE:
                    return True
                return False
            if day < 5 and time >= EQUITY_OPEN and time <= EQUITY_CLOSE:
                return True
            return False
        # all other markets (crypto, fx, metal)
        return True
