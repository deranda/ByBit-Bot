
class KDJStrategy:
    def __init__(self):
        self.trigger = None
        self.sr_lines = []
        self.supports = []
        self.resistances = []
        self.offset = 0

        self.open_short_counter = 0
        self.close_short_counter = 0
        self.open_long_counter = 0
        self.close_long_counter = 0

    def populate_indicators(self, df):
        self.offset = 0

        # KDJ - Default 14/6/4/ - test 14/3/4
        a = 8  # k-length
        b = 4  # k-smoothing
        c = 4  # d-smoothing
        if len(df) > 0:
            _L = df['low'].rolling(a).min()
            _H = df['high'].rolling(a).max()
            df['K'] = 100 * (df['close'] - _L) / (_H - _L)  # blue
            df['K'] = round(df['K'].rolling(b).mean(), 2)
            df['D'] = round(df['K'].rolling(c).mean(), 2)  # orange
            df['J'] = round(3 * df['K'] - 2 * df['D'], 2)
        self.offset = max(self.offset, a+b+c-3)

        return df, self.offset

    def populate_trigger(self, df):
        max_triggers = 1
        self.open_short_counter = 0
        self.close_short_counter = 0
        self.open_long_counter = 0
        self.close_long_counter = 0

        # KDJ - Trigger
        # KDJ-buy signal
        k_buy = 27
        # KDF-sell signal
        k_sell = 75
        if df['K'].iloc[-3] < df['D'].iloc[-3] and df['K'].iloc[-2] > df['D'].iloc[-2]:
            self.close_short_counter += 1
            self.open_long_counter += 1

        if df['K'].iloc[-3] > df['D'].iloc[-3] and df['K'].iloc[-2] < df['D'].iloc[-2]:
            self.close_long_counter += 1
            self.open_short_counter += 1

        # evaluate triggers
        self.trigger = []
        if self.close_short_counter == max_triggers:
            self.trigger.append('close_short')
        if self.open_short_counter == max_triggers:
            self.trigger.append('open_short')
        if self.close_long_counter == max_triggers:
            self.trigger.append('close_long')
        if self.open_long_counter == max_triggers:
            self.trigger.append('open_long')

        return self.trigger
