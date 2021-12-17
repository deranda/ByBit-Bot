from datetime import datetime
from pybit import HTTP
import pybit
import pandas as pd
import requests
import datetime as dt
import calendar
import time

import config
import kdj_strategy


# ToDo: Check TakeProfit (seems to be calculated by leverage*config.take_profit)
class Bot:
    def __init__(self, api_key=config.api_key, secret_key=config.api_secret, error_log=config.error_file,
                 trade_log=config.trade_file, trade_hist_log=config.trade_hist_file, log=config.log_file,
                 mode=config.mode, symbol=config.symbol, max_trades=config.max_open_trades, tf=config.timeframe):
        print(str(datetime.utcnow()) + ': Creating new Bot', flush=True)
        self.session = HTTP("https://api.bybit.com", api_key=api_key, api_secret=secret_key)
        print(str(datetime.utcnow()) + ': Session has been created.', flush=True)

        print(str(datetime.utcnow()) + ': Creating Log-reports...', flush=True)
        self.error_log = error_log
        self.trade_log = trade_log
        self.trade_history_log = trade_hist_log
        self.log = log
        write_str = str(datetime.utcnow()) + ': Crypto Bot started. \n'
        with open(self.error_log, 'w', encoding='utf-8') as f:
            f.write(write_str)
            f.close()
        with open(self.trade_log, 'w') as f:
            f.write(write_str)
            f.close()
        with open(self.log, 'w') as f:
            f.write(write_str)
            f.close()
        try:
            with open(self.trade_history_log, 'a') as f:
                f.close()
        except IOError:
            with open(self.trade_history_log, 'w') as f:
                f.close()
        print(str(datetime.utcnow()) + ': Creating Log-reports done.', flush=True)

        print(str(datetime.utcnow()) + ': Reading trading parameters...', flush=True)
        self.trading_mode = mode
        self.symbol = symbol
        self.max_open_trades = max_trades
        self.time_frame = tf
        self.df = pd.DataFrame()
        self.trade_history = []
        self.supports = []
        self.resistances = []
        self.trigger = None
        self.strategy = kdj_strategy.KDJStrategy()
        print(str(datetime.utcnow()) + ': Reading trading parameters done.', flush=True)

        wallet_usd = self.get_wallet()
        print(str(datetime.utcnow()) + ': Wallet balance:' + str(wallet_usd) + ' USDT', flush=True)
        if config.enable_telegram:
            self.write_telegram_msg(str(datetime.utcnow()) + ': Crypto Bot started in \"' + config.mode + '\" mode.')
            self.write_telegram_msg(str(datetime.utcnow()) + ': Wallet balance:' + str(wallet_usd) + ' USDT')
        self.positions = []
        pos = self.get_position(0)
        if len(pos) > 0:
            self.positions.append(pos)
        self.print_active_position()

    # --- Get Exchange interaction methods ---
    def get_price(self):
        try:
            response = self.session.latest_information_for_symbol(symbol=config.symbol)['result']
            df = pd.DataFrame(response)
            price = float(df['last_price'])
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
            price = 0.0
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
            price = 0.0
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
            price = 0.0
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
            price = 0.0
        return price

    def get_position(self, created_at):
        # [0] timestamp opened position
        # [1] entry_price: price at buying time
        # [2] size: Order size [USD]
        # [3] side: Long/Short
        # [4] leverage: leverage
        # [5] stop_loss: stop loss
        # [6] take_profit: take profit
        try:
            position = []
            bybit_response = self.session.my_position(symbol=self.symbol)['result']
            if bybit_response[0]['size'] > 0:
                response = bybit_response[0]
            elif bybit_response[1]['size'] > 0:
                response = bybit_response[1]
            else:
                response = {'side': 'None'}
            if response['side'] != 'None':
                if response['side'] == 'Buy':
                    pos_type = 'Long'
                elif response['side'] == 'Sell':
                    pos_type = 'Short'
                else:
                    pos_type = ''
                position.append(created_at)
                position.append(round(float(response['entry_price']), 1))  # [1] entry_price: price at buying time
                position.append(round(float(response['size']), 5))  # [2] size: Order size [BTC]
                position.append(pos_type)  # [3] side: Long/Short
                position.append(round(float(response['leverage']), 0))  # [4] leverage: leverage
                position.append(round(float(response['stop_loss']), 1))  # [5] stop_loss: stop loss
                position.append(round(float(response['take_profit']), 1))  # [6] take_profit: take profit
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
            position = []
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
            position = []
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
            position = []
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
            position = []

        return position

    def get_wallet(self):
        try:
            usd = float(self.session.get_wallet_balance(coin="USDT")['result']['USDT']['available_balance'])
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
            usd = 0.0
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
            usd = 0.0
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
            usd = 0.0
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
            usd = 0.0
        return round(usd, 2)

    def get_dataframe(self, timestamp, limit):
        try:
            response = self.session.query_kline(symbol=self.symbol, interval=self.time_frame, from_time=timestamp,
                                                limit=limit)['result']
            df = pd.DataFrame.from_dict(response)
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
            response = None
            df = pd.DataFrame(response)
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
            response = None
            df = pd.DataFrame(response)
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
            response = None
            df = pd.DataFrame(response)
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
            response = None
            df = pd.DataFrame(response)

        if len(df) > 0:
            df['open_time'] = pd.to_numeric(df['open_time'], errors='coerce')
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        return df

    def get_history_dataframes(self, year, month, day, hour=0, minute=0):
        lim = 200
        timestamp = calendar.timegm(dt.datetime(year, month, day, hour, minute).utctimetuple())
        df_history = self.get_dataframe(timestamp, lim)
        if len(df_history) == 0:
            print(str(datetime.utcnow()) + 'Error reading history data frames: empty data frame. \n' +
                  'Maybe request error: to many requests sent.', flush=True)
            exit()
        else:
            timestamp = timestamp + lim * self.time_frame * 60
            while True:
                new_df = self.get_dataframe(timestamp, lim)
                if len(new_df) == 0:
                    break
                else:
                    df_history = df_history.append(new_df, ignore_index=True)
                    timestamp = timestamp + lim * self.time_frame * 60
            df_history['open_time'] = pd.to_numeric(df_history['open_time'], errors='coerce')
            df_history['open'] = pd.to_numeric(df_history['open'], errors='coerce')
            df_history['close'] = pd.to_numeric(df_history['close'], errors='coerce')
            df_history['high'] = pd.to_numeric(df_history['high'], errors='coerce')
            df_history['low'] = pd.to_numeric(df_history['low'], errors='coerce')
            df_history['volume'] = pd.to_numeric(df_history['volume'], errors='coerce')
            log_msg = str(datetime.utcnow()) + ': Reading exchange history done. ' + str(len(df_history)) + \
                      ' candle(s) has been red.'
            print(log_msg, flush=True)
            self.write_to_log(log_msg)
        return df_history

    # --- Set Exchange interaction methods ---
    def set_leverage(self):
        try:
            self.session.set_leverage(symbol=self.symbol,
                                      buy_leverage=config.leverage,
                                      sell_leverage=config.leverage)
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)

    def set_stop_loss(self, sl, side):
        try:
            self.session.set_trading_stop(symbol=self.symbol, side=side, stop_loss=sl)
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)

    # --- Exchange interaction methods for orders and positions ---
    def place_order(self, side):
        # self.set_leverage()
        wallet_usd = self.get_wallet()
        current_price = self.get_price()
        order_amount = round(config.order_amount * wallet_usd / current_price * config.leverage, 5)
        if side == 'Long':
            side = "Buy"
        elif side == 'Short':
            side = "Sell"
        if side == "Buy":
            sl = int(round(current_price * (1 - config.stop_loss / config.leverage), 1))
            tp = int(round(current_price * (1 + config.take_profit), 1))
        elif side == "Sell":
            sl = int(round(current_price * (1 + config.stop_loss / config.leverage), 1))
            tp = int(round(current_price * (1 - config.take_profit), 1))
        else:
            sl = 0
            tp = 0
        try:
            self.session.place_active_order(
                side=side,
                symbol=self.symbol,
                order_type="Market",
                qty=order_amount,
                time_in_force="GoodTillCancel",
                close_on_trigger=False,
                reduce_only=False,
                take_profit=tp,
                stop_loss=sl
            )
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
        try:
            response = self.session.get_active_order(symbol=self.symbol, order_status="New")['result']['data']
            if response is None:
                response = []
            while len(response) != 0:
                time.sleep(1)
                try:
                    response = self.session.get_active_order(symbol=self.symbol, order_status="New")['result']['data']
                except pybit.exceptions.FailedRequestError as ex:
                    self.write_error_log(ex)
                except pybit.exceptions.InvalidRequestError as ex:
                    self.write_error_log(ex)
                except requests.exceptions.Timeout as ex:
                    self.write_error_log(ex)
                except requests.exceptions.ConnectionError as ex:
                    self.write_error_log(ex)
        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
        pos = self.get_position(time.time())
        self.positions.append(pos)
        self.write_trade_log('open', pos)
        return pos

    def close_active_position(self):
        pos = self.get_position(0)
        if len(pos) > 0:
            if pos[3] == "Short":
                side = "Buy"
            elif pos[3] == "Long":
                side = "Sell"
            else:
                side = None
            try:
                self.session.place_active_order(
                    side=side,
                    symbol=self.symbol,
                    order_type="Market",
                    qty=pos[2],
                    time_in_force="GoodTillCancel",
                    close_on_trigger=False,
                    reduce_only=True
                )
            except pybit.exceptions.FailedRequestError as ex:
                self.write_error_log(ex)
            except pybit.exceptions.InvalidRequestError as ex:
                self.write_error_log(ex)
            except requests.exceptions.Timeout as ex:
                self.write_error_log(ex)
            except requests.exceptions.ConnectionError as ex:
                self.write_error_log(ex)
            try:
                response = self.session.get_active_order(symbol=self.symbol, order_status="New")['result']['data']
                while response is not None:
                    time.sleep(1)
                    try:
                        response = self.session.get_active_order(symbol=self.symbol,
                                                                 order_status="New")['result']['data']
                    except pybit.exceptions.FailedRequestError as ex:
                        self.write_error_log(ex)
                    except pybit.exceptions.InvalidRequestError as ex:
                        self.write_error_log(ex)
                    except requests.exceptions.Timeout as ex:
                        self.write_error_log(ex)
                    except requests.exceptions.ConnectionError as ex:
                        self.write_error_log(ex)

            except pybit.exceptions.FailedRequestError as ex:
                self.write_error_log(ex)
            except pybit.exceptions.InvalidRequestError as ex:
                self.write_error_log(ex)
            except requests.exceptions.Timeout as ex:
                self.write_error_log(ex)
            except requests.exceptions.ConnectionError as ex:
                self.write_error_log(ex)
            close_price = self.get_price()
            pos.append(close_price)  # [7] close price
            if pos[3] == "Short":
                win_rate = (1 - close_price / pos[1]) * pos[4]
            elif pos[3] == "Long":
                win_rate = (close_price / pos[1] - 1) * pos[4]
            else:
                win_rate = 1
            pos.append(win_rate)  # [8] win rate
            abs_win = pos[2] * win_rate
            pos.append(abs_win)  # [9] abs win
            self.write_trade_log('close', pos)
            self.trade_history.append(pos)
            self.write_trade_history_log(pos)
            self.positions.pop(0)

    # --- Data processing methods ---
    def add_new_dataframe(self):
        now = datetime.utcnow()
        unix_time = calendar.timegm(now.utctimetuple())
        since = unix_time - self.time_frame * 2 * 60
        new_df = self.get_dataframe(since, 10)
        if len(new_df) > 0:
            if new_df['open_time'].iloc[-1] == self.df['open_time'].iloc[-1]:
                # update current candle
                self.df.drop(index=self.df.tail(1).index, inplace=True)
                self.df = self.df.append(new_df.iloc[-1], ignore_index=True)
                self.df, offset = self.strategy.populate_indicators(self.df)
            else:
                # Print candle if the candle is new
                self.df = self.df.append(new_df.iloc[-1], ignore_index=True)
                self.df, off = self.strategy.populate_indicators(self.df)
                write_str = str(now) + ' - open_time:' + str(self.df['open_time'].iloc[-1]) + ' open:' + \
                            str(self.df['open'].iloc[-1]) + ' close:' + str(self.df['close'].iloc[-1]) + ' volume:' + \
                            str(self.df['volume'].iloc[-1]) + ' high:' + str(self.df['high'].iloc[-1]) + ' low:' + \
                            str(self.df['low'].iloc[-1])
                self.write_to_log(write_str)
                print(write_str, flush=True)
                write_str = str(now) + ' - K:' + str(self.df.iloc[-1]['K']) + ' D:' + str(self.df.iloc[-1]['D']) + \
                            ' J:' + str(self.df.iloc[-1]['J'])
                self.write_to_log(write_str)
                print(write_str, flush=True)

    def read_historical_data(self):
        self.df = self.get_history_dataframes(2018, 12, 1)

    def validate_sl_tp(self):
        for pos in self.positions:
            max_price = self.df['high'].iloc[-1]
            min_price = self.df['low'].iloc[-1]
            if len(pos) > 0:
                sl = pos[5]
                tp = pos[6]
                if pos[3] == 'Long':
                    if sl != 0.0 and min_price < sl:
                        print('close Long position due to SL', flush=True)
                        pos.append(sl)
                        win_rate = (sl / pos[1] - 1) * pos[4]
                        pos.append(win_rate)
                        abs_win = pos[2] * win_rate
                        pos.append(abs_win)
                        self.write_trade_log('close', pos)
                        self.positions.pop()
                        self.trade_history.append(pos)
                        self.write_trade_history_log(pos)
                    if tp != 0.0 and max_price > tp:
                        print('close Long position due to TP', flush=True)
                        pos.append(tp)
                        win_rate = (tp / pos[1] - 1) * pos[4]
                        pos.append(win_rate)
                        abs_win = pos[2] * win_rate
                        pos.append(abs_win)
                        self.write_trade_log('close', pos)
                        self.positions.pop()
                        self.trade_history.append(pos)
                        self.write_trade_history_log(pos)
                else:
                    if sl != 0.0 and max_price > sl:
                        print('close Short position due to SL', flush=True)
                        pos.append(sl)
                        win_rate = (1 - sl / pos[1]) * pos[4]
                        pos.append(win_rate)
                        abs_win = pos[2] * win_rate
                        pos.append(abs_win)
                        self.positions.pop()
                        self.trade_history.append(pos)
                        self.write_trade_history_log(pos)
                    if tp != 0.0 and min_price < tp:
                        print('close Short position due to TP', flush=True)
                        pos.append(tp)
                        win_rate = (1 - tp / pos[1]) * pos[4]
                        pos.append(win_rate)
                        abs_win = pos[2] * win_rate
                        pos.append(abs_win)
                        self.write_trade_log('close', pos)
                        self.positions.pop()
                        self.trade_history.append(pos)
                        self.write_trade_history_log(pos)

    def adjust_stop_loss(self):
        for position in self.positions:
            if position[3] == 'Long':
                if ((self.df['close'].iloc[-1] / position[1]) - 1) > 0.03:
                    new_sl = (1 + 0.005) * position[1]
                    self.set_stop_loss(new_sl, 'Buy')
                    self.positions[self.positions.index(position)][5] = new_sl
            elif position[3] == 'Short':
                if (1 - (self.df['close'].iloc[-1] / position[1])) > 0.03:
                    new_sl = (1 - 0.005) * position[1]
                    self.set_stop_loss(new_sl, 'Sell')
                    self.positions[self.positions.index(position)][5] = new_sl

    # --- Write and print methods ---
    def write_error_log(self, ex):
        write_str = str(datetime.utcnow()) + ': ' + str(ex)
        with open(self.error_log, 'a', encoding='utf-8') as f:
            f.write(write_str + '\n')
            f.close()
        print(write_str, flush=True)

    def write_to_log(self, msg):
        with open(self.log, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
            f.close()

    def write_trade_log(self, side, position):
        # [0] timestamp opened position
        # [1] entry_price: price at buying time
        # [2] size: Order size [USD]
        # [3] side: Long/Short
        # [4] leverage: leverage
        # [5] stop_loss: stop loss
        # [6] take_profit: take profit
        # [7] close price
        # [8] win rate
        # [9] abs win
        if len(position) > 0:
            write_str = ''
            if side == 'close':
                write_str = str(datetime.utcnow()) + ': Closed ' + str(position[3]) + ' position at ' + \
                            str(position[7]) + ' USD. Entry price: ' + str(position[1]) + \
                            ' USD. Trade closed with win rate: ' + str(position[8]) + '% and an absolute win of: ' +\
                            str(position[9]) + ' USD.'
            elif side == 'open':
                write_str = str(datetime.utcnow()) + ': Opened a new ' + str(position[3]) + ' position at ' \
                            + str(position[1]) + 'USD. Stop loss: ' + str(position[5]) + ' USD. Take profit: ' \
                            + str(position[6]) + 'USD.'
            with open(self.trade_log, 'a') as f:
                f.write(write_str + '\n')
                f.close()
            if config.enable_telegram:
                self.write_telegram_msg(write_str)
                print(write_str, flush=True)

    def write_trade_history_log(self, position):
        # [0] timestamp opened position
        # [1] entry_price: price at buying time
        # [2] size: Order size [USD]
        # [3] side: Long/Short
        # [4] leverage: leverage
        # [5] stop_loss: stop loss
        # [6] take_profit: take profit
        # [7] close price
        # [8] win rate
        # [9] abs win
        if len(position) > 0:
            write_str = str(datetime.utcnow()) + ': Closed ' + str(position[3]) + ' position at ' + \
                        str(position[7]) + ' USD. Entry price: ' + str(position[1]) + \
                        ' USD. Trade closed with win rate: ' + str(position[8]) + '% and an absolute win of: ' +\
                        str(position[9]) + ' USD.'
            with open(self.trade_history_log, 'a') as f:
                f.write(write_str + '\n')
                f.close()

    def print_active_position(self):
        if len(self.positions) == 0:
            write_str = str(datetime.utcnow()) + ': Currently, there are no active positions.'
            print(write_str + '\n', flush=True)
            if config.enable_telegram:
                self.write_telegram_msg(write_str)
        else:
            for pos in self.positions:
                write_str = str(datetime.utcnow()) + ': Side: ' + str(pos[3]) + '. Size: ' + str(pos[2]) + \
                            ' BTC. Entry price: ' + str(pos[1]) + ' BTCUSD. Leverage: ' + str(pos[4]) + \
                            '. Stop loss: ' + str(pos[5]) + ' USD. Take profit: ' + str(pos[6]) + ' USD.'
                print(write_str + '\n', flush=True)
                if config.enable_telegram:
                    self.write_telegram_msg(write_str)

    @staticmethod
    def write_telegram_msg(msg):
        send_text = 'https://api.telegram.org/bot' + config.telegram_token + '/sendMessage?chat_id=' + \
                    config.telegram_chatID + '&parse_mode=Markdown&text=' + msg
        response = requests.get(send_text)
        return response.json()

    # --- Backtest methods ---
    def convert_backtest_starting_time(self, t):
        now = datetime.now()
        time_space = t[-1]
        time_quantity = int(t[0:-1])
        if time_space == "Y":
            delta_t = 365
        elif time_space == "M":
            delta_t = 30
        elif time_space == "W":
            delta_t = 7
        elif time_space == "D":
            delta_t = 1
        else:
            print('Backtest: invalid time. Backtesting for 1 Year.', flush=True)
            time_quantity = 1
            delta_t = 365
        now += dt.timedelta(days=-1 * time_quantity * delta_t)
        trash, offset = self.strategy.populate_indicators(pd.DataFrame())
        now += dt.timedelta(minutes=-1 * self.time_frame * offset)
        return now

    def backtest(self, t):
        filename = 'Backtest' + str(time.time()) + '.dat'
        with open(filename, 'w') as f:
            f.write('Start backtesting')
            f.close()
        buy_trades = [[], []]
        sell_sl_trades = [[], []]
        sell_tr_trades = [[], []]
        sl_counter = 0
        tp_counter = 0
        tr_counter = 0
        trade_counter = 0
        flat_win_rate = 0
        wallet = 1

        # Loading dataframes
        print(str(datetime.utcnow()) + ': Loading history data', flush=True)
        now = self.convert_backtest_starting_time(t)
        self.df = self.get_history_dataframes(now.year, now.month, now.day)

        # Loading strategy
        print(str(datetime.utcnow()) + ': Loading strategy', flush=True)
        self.df, offset = self.strategy.populate_indicators(self.df)

        # Running backtest
        print(str(datetime.utcnow()) + ': Running backtest', flush=True)
        n = range(offset, len(self.df), 1)
        for i in n:
            # check stop loss and take profit
            for position in self.positions:
                if position[3] == 'Short':
                    if self.df['high'][i] >= position[5]:
                        win_rate = self.close_backtest_order(position[5], 'stop loss', self.df['open_time'][i],
                                                             filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        sl_counter += 1
                    if self.df['high'][i] <= position[6]:
                        win_rate = self.close_backtest_order(position[6], 'take profit', self.df['open_time'][i],
                                                             filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        tp_counter += 1
                elif position[3] == 'Long':
                    if self.df['low'][i] <= position[5]:
                        win_rate = self.close_backtest_order(position[5], 'stop loss', self.df['open_time'][i],
                                                             filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        sl_counter += 1
                    if self.df['high'][i] >= position[6]:
                        win_rate = self.close_backtest_order(position[6], 'take profit', self.df['open_time'][i],
                                                             filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        tp_counter += 1

            # check triggers
            self.trigger = self.strategy.populate_trigger(self.df.iloc[0:i])
            if self.trigger is not None:
                if self.trigger == 'Long':
                    for position in self.positions:
                        if position[3] == 'Short':
                            win_rate = self.close_backtest_order(self.df['open'][i], 'trigger',
                                                                 self.df['open_time'][i], filename)
                            flat_win_rate += win_rate*config.order_amount
                            wallet += wallet*config.order_amount*win_rate
                            tr_counter += 1
                if self.trigger == 'Short':
                    for position in self.positions:
                        if position[3] == 'Long':
                            win_rate = self.close_backtest_order(self.df['open'][i], 'trigger',
                                                                 self.df['open_time'][i], filename)
                            flat_win_rate += win_rate*config.order_amount
                            wallet += wallet*config.order_amount*win_rate
                            tr_counter += 1

                # place a new order
                if len(self.positions) < self.max_open_trades:
                    position = self.place_backtest_order(self.df['open_time'][i], self.df['open'][i],
                                                         wallet, self.trigger)
                    self.positions.append(position)
                    trade_counter += 1

        print(str(datetime.utcnow()) + ': Backtest done.', str(trade_counter), 'trades have been made with total',
              str(round((wallet-1)*100, 2)), '% win-rate. The trades were canceled', str(sl_counter),
              'times by stop loss,', str(tp_counter), 'times by take profit and', str(tr_counter),
              'times by trigger threshold. The flat win rate would have been:', str(round(flat_win_rate*100, 2)), '%',
              flush=True)

        if config.plot:
            import matplotlib.pyplot as plt
            stamps = self.df['open_time']
            dates_list = [datetime.fromtimestamp(date) for date in stamps]
            fig, axs = plt.subplots(2, 1)
            axs[0].plot(dates_list, self.df['open'], 'b',
                        buy_trades[0], buy_trades[1], 'r*',
                        sell_sl_trades[0], sell_sl_trades[1], 'g*',
                        sell_tr_trades[0], sell_tr_trades[1], 'y*')
            axs[0].grid(b=True, which='major', color='k', linestyle='-')
            axs[0].grid(b=True, which='minor', color='k', linestyle='--')
            axs[0].set_xlim(dates_list[0], dates_list[len(dates_list)-1])
            if 'kdj' in config.triggers:
                axs[1].plot(dates_list, self.df['K'], 'b',
                            dates_list, self.df['D'], 'r')
                axs[1].grid(b=True, which='major', color='k', linestyle='-')
                axs[1].grid(b=True, which='minor', color='k', linestyle='--')
                axs[1].set_xlim(dates_list[0], dates_list[len(dates_list)-1])
            plt.show()

    def close_backtest_order(self, close_price, reason, close_time, file):
        # Position structure
        # [0] open-timestamp
        # [1] entry price
        # [2] Order size [USD]
        # [3] side (Long/Short)
        # [4] leverage
        # [5] stop loss
        # [6] take profit
        position = self.positions[0]
        if position[3] == 'Short':
            profit = (1 - close_price / position[1]) * position[4]
        elif position[3] == 'Long':
            profit = (close_price / position[1] - 1) * position[4]
        else:
            profit = 0
        with open(file, 'a') as f:
            write_str = '\n' + ': Close ' + str(position[3]) + ' position at: ' \
                         + str(round(close_price, 1)) + ' USD/BTC by ' + reason + '. Order amount: ' + str(position[2])\
                         + ' with leverage: ' + str(position[4]) + '. Win-rate: ' + str(round(profit * 100, 2)) + '%.'
            f.write(write_str)
            f.close()
        # trade_history structure
        # [0] open timestamp
        # [1] open price
        # [2] Order size [USD]
        # [3] side (Long/Short)
        # [4] leverage
        # [5] stop loss
        # [6] take profit
        # [7] close timestamp
        # [8] close price
        # [9] profit (=leverage * [8]/[1])
        position.append(close_time)
        position.append(close_price)
        position.append(profit)
        self.trade_history.append(position)
        self.positions.pop(0)
        return profit

    @staticmethod
    def place_backtest_order(open_time, open_price, wallet, side):
        # Position structure
        # [0] open-timestamp
        # [1] entry price
        # [2] Order size [USD]
        # [3] side (Long/Short)
        # [4] leverage
        # [5] stop loss
        # [6] take profit
        if side == 'Short':
            sl = open_price * (1+config.stop_loss/config.leverage)
            tp = open_price * (1-config.take_profit)
        elif side == 'Long':
            sl = open_price * (1-config.stop_loss/config.leverage)
            tp = open_price * (1+config.take_profit)
        else:
            sl = 0.0
            tp = 0.0
        return [open_time, open_price, wallet*config.order_amount, side, config.leverage, sl, tp]
