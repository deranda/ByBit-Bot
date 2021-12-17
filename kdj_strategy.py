import config


class KDJStrategy:
    def __init__(self):
        self.trigger = None
        self.sr_lines = []
        self.supports = []
        self.resistances = []
        self.offset = 0

        self.buy_counter = 0
        self.sell_counter = 0
        pass

    def populate_indicators(self, df):
        self.offset = 0

        # MACD - Default 12/26/9 - test 12/20/9
        if 'macd' in config.triggers:
            macd_short = 12
            macd_long = 26
            macd_signal = 9
            if len(df) > 0:
                df['macd'] = df['close'].ewm(span=macd_short, adjust=False).mean() - \
                             df['close'].ewm(span=macd_long, adjust=False).mean()
                df['macd_signal'] = df['macd'].ewm(span=macd_signal, adjust=False).mean()
            self.offset = max(self.offset, macd_long-1)

        # KDJ - Default 14/1/3/ - test 14/3/4
        if 'kdj' in config.triggers:
            a = 14  # k-length
            b = 6  # k-smoothing
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
        self.buy_counter = 0
        self.sell_counter = 0
        # MACD - Trigger
        if 'macd' in config.triggers:
            diff2 = df['macd_signal'].iloc[-3] - df['macd'].iloc[-3]  # before (<0:MACD>Signal)
            diff1 = df['macd_signal'].iloc[-2] - df['macd'].iloc[-2]  # afterwards (<0:MACD>Signal)
            if diff2 < 0 < diff1:  # before: MACD>signal, afterwards: MACD<signal -> MACD crosses downwards
                self.sell_counter += 1
            if diff2 > 0 > diff1:  # before: MACD>signal, afterwards: MACD<signal -> MACD crosses upwards
                self.buy_counter += 1

        # KDJ - Trigger
        if 'kdj' in config.triggers:
            # KDJ-buy signal
            k_buy = 27
            # KDF-sell signal
            k_sell = 75
            if df['K'].iloc[-2] < k_buy <= df['K'].iloc[-3]:
                self.buy_counter += 1
            if df['K'].iloc[-2] > k_sell >= df['K'].iloc[-3]:
                self.sell_counter += 1

        # evaluate triggers
        if self.buy_counter == len(config.triggers):
            self.trigger = 'Long'
        elif self.sell_counter == len(config.triggers):
            self.trigger = 'Short'
        else:
            self.trigger = None

        if config.enable_sr_lines:
            if self.trigger == 'Short':
                for sup in self.supports:
                    if 0 < (1 - (sup / df['close'].iloc[-1])) < config.sr_range:
                        self.trigger = None
            elif self.trigger == 'Long':
                for res in self.resistances:
                    if 0 < (1 - (df['close'].iloc[-1]) / res) < config.sr_range:
                        self.trigger = None
            # else: if price approaches s-line -> go long, if price approaches r-line -> go short?

        return self.trigger

    def add_sr_line(self, sr):
        self.sr_lines.append(sr)

    def sort_sr_lines(self, df):
        for line in self.sr_lines:
            if line > df['close'].iloc[-1]:
                self.resistances.append(line)
            else:
                self.supports.append(line)
