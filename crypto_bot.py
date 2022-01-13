from datetime import datetime
from pybit import HTTP
import pybit
import pandas as pd
import requests
import datetime as dt
import calendar
import time
from telegram.ext import *
import sys
import importlib

import config
import kdj_strategy


# ToDo: telegram close position
class Bot:
    def __init__(self, api_key=config.api_key, secret_key=config.api_secret, error_log=config.error_file,
                 trade_log=config.trade_file, trade_hist_log=config.trade_hist_file, log=config.log_file,
                 mode=config.mode, symbol=config.symbol, max_trades=config.max_open_trades, tf=config.timeframe):
        print(str(datetime.utcnow()) + ': Creating new Bot', flush=True)
        if not config.test_net_enabled:
            self.session = HTTP("https://api.bybit.com",
                                api_key=api_key,
                                api_secret=secret_key,
                                recv_window=10000)
        else:
            self.session = HTTP("https://api-testnet.bybit.com",
                                api_key="yE7OtL62tMM2G1Uua0",
                                api_secret="NmHKVpUOM8nREHwFgsqQEH6MfPzKYPag77UC",
                                recv_window=10000)

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

        self.trading_mode = mode
        self.trading_enabled = True
        self.symbol = symbol
        self.set_leverage()
        self.max_open_trades = max_trades
        self.time_frame = tf
        self.df = pd.DataFrame()
        self.trade_history = []
        self.supports = []
        self.resistances = []
        self.trigger = None
        self.strategy = kdj_strategy.KDJStrategy()
        self.candle_keys = ['open_time', 'symbol', 'period', 'volume', 'open', 'high', 'low', 'close']
        self.indicators = ['K', 'D', 'J']
        self.tel_commands = ["start", "stop", "help", "status", "position", "candle", "history", "closeposition",
                             "resetwarning"]
        self.warning_sent = False

        wallet_usd = self.get_wallet()
        if config.enable_telegram:
            self.setup_telegram_bot()
            self.send_telegram_msg(str(datetime.utcnow()) + ': Crypto Bot started in \"' + config.mode + '\" mode.')
            self.send_telegram_msg(str(datetime.utcnow()) + ': Wallet balance:' + str(wallet_usd) + ' USDT')
        self.positions = []
        pos = self.get_position(0)
        if len(pos) > 0:
            self.positions.append(pos)
        self.previous_positions = self.positions

    # --- Get Exchange interaction methods ---
    def get_price(self):
        received_request = False
        request_delay = 1
        max_retries = 10
        request_counter = 0
        price = 0.0
        while not received_request:
            try:
                response = self.session.latest_information_for_symbol(symbol=config.symbol)['result']
                df = pd.DataFrame(response)
                price = float(df['last_price'])
                received_request = True
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
            request_counter += 1
            if request_counter == max_retries:
                received_request = True
                print(str(datetime.utcnow()) + '(utc): Max retries in bot.get_price() reached.', flush=True)
            time.sleep(request_delay)
        return price

    def get_position(self, created_at):
        # [0] timestamp opened position
        # [1] entry_price: price at buying time
        # [2] size: Order size [USD]
        # [3] side: Long/Short
        # [4] leverage: leverage
        # [5] stop_loss: stop loss
        # [6] take_profit: take profit
        max_retries = 10
        request_counter = 0
        request_delay = 1
        position = []
        received_request = False
        while not received_request:
            try:
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
                received_request = True
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
            request_counter += 1
            if request_counter == max_retries:
                received_request = True
                print(str(datetime.utcnow()) + '(utc): Max retries in bot.get_position() reached.', flush=True)
            time.sleep(request_delay)
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

    def get_dataframe(self, timestamp, limit, tf):
        try:
            response = self.session.query_kline(symbol=self.symbol, interval=tf, from_time=timestamp,
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

    def get_full_history_dataframes(self):
        lim = 200
        timestamp = calendar.timegm(dt.datetime(2000, 1, 1, 0, 0).utctimetuple())
        df_history = self.get_dataframe(timestamp, lim, config.timeframe)
        timestamp = df_history['open_time'].iloc[-1] + config.timeframe * 60
        while True:
            new_df = self.get_dataframe(timestamp, lim, config.timeframe)
            if len(new_df) == 0:
                break
            else:
                df_history = df_history.append(new_df, ignore_index=True)
                timestamp = df_history['open_time'].iloc[-1] + config.timeframe * 60
        df_history['open_time'] = pd.to_numeric(df_history['open_time'], errors='coerce')
        df_history['open_date'] = [datetime.utcfromtimestamp(int(d)) for d in df_history['open_time']]
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

    def get_history_dataframes(self, year=2000, month=1, day=1, hour=0, minute=0):
        lim = 200
        timestamp = calendar.timegm(dt.datetime(year, month, day, hour, minute).utctimetuple())
        if self.time_frame == 180 and config.symbol == "BTCUSDT":
            time_frame = 60
        else:
            time_frame = self.time_frame
        df_history = self.get_dataframe(timestamp, lim, time_frame)
        if len(df_history) == 0:
            print(str(datetime.utcnow()) + 'Error reading history data frames: empty data frame. \n' +
                  'Maybe request error: to many requests sent.', flush=True)
            exit()
        else:
            timestamp = timestamp + lim * time_frame * 60
            while True:
                new_df = self.get_dataframe(timestamp, lim, time_frame)
                if len(new_df) == 0:
                    break
                else:
                    df_history = df_history.append(new_df, ignore_index=True)
                    timestamp = timestamp + lim * time_frame * 60
            df_history['open_time'] = pd.to_numeric(df_history['open_time'], errors='coerce')
            df_history['open_date'] = [datetime.utcfromtimestamp(int(d)) for d in df_history['open_time']]
            df_history['open'] = pd.to_numeric(df_history['open'], errors='coerce')
            df_history['close'] = pd.to_numeric(df_history['close'], errors='coerce')
            df_history['high'] = pd.to_numeric(df_history['high'], errors='coerce')
            df_history['low'] = pd.to_numeric(df_history['low'], errors='coerce')
            df_history['volume'] = pd.to_numeric(df_history['volume'], errors='coerce')
            if self.time_frame == 180 and config.symbol == "BTCUSDT":
                df_history = self.convert_1h_to_3h_dataframe(df_history)
            log_msg = str(datetime.utcnow()) + ': Reading exchange history done. ' + str(len(df_history)) + \
                      ' candle(s) has been red.'
            print(log_msg, flush=True)
            self.write_to_log(log_msg)
        return df_history

    @staticmethod
    def convert_1h_to_3h_dataframe(df):
        data = {}
        cat_3rd_start = ['id', 'symbol', 'start_at', 'open_time', 'open', 'turnover']
        cat_3rd_end = ['close']
        cat_stay = ['period', 'interval']
        for i in cat_3rd_start:
            data[i] = df[i].values.tolist()[::3]
        for i in cat_3rd_end:
            val_list = df[i].values.tolist()
            val_list.pop(0)
            val_list.pop(0)
            data[i] = val_list[::3]
        for i in cat_stay:
            data[i] = len(data['symbol'])*[180]

        vol_list = []
        high_list = []
        low_list = []
        temp_vol = []
        temp_high = []
        temp_low = []
        data_vol_list = df['volume'].values.tolist()
        data_high_list = df['high'].values.tolist()
        data_low_list = df['low'].values.tolist()
        j = 0
        for k in range(len(data_vol_list)):
            temp_vol.append(data_vol_list[k])
            temp_high.append(data_high_list[k])
            temp_low.append(data_low_list[k])
            j += 1
            if j == 3:
                vol_list.append(sum(temp_vol))
                high_list.append(max(temp_high))
                low_list.append(min(temp_low))
                j = 0
                temp_vol = []
                temp_high = []
                temp_low = []
        data['volume'] = vol_list
        data['high'] = high_list
        data['low'] = low_list
        for i in data:
            data[i] = data[i][:len(data['close'])]
        pd_data = {'id': data['id'],
                   'symbol': data['symbol'],
                   'period': data['period'],
                   'interval': data['interval'],
                   'start_at': data['start_at'],
                   'open_time': data['open_time'],
                   'volume': data['volume'],
                   'open': data['open'],
                   'high': data['high'],
                   'low': data['low'],
                   'close': data['close'],
                   'turnover': data['turnover']}
        df = pd.DataFrame.from_dict(pd_data)
        df['open_date'] = [datetime.utcfromtimestamp(int(d)) for d in df['open_time']]

        return df

    def get_order_history(self, lim=50):
        try:
            bybit_conditional_order_history = self.session.get_conditional_order(symbol=self.symbol,
                                                                                 limit=50)['result']['data']
            bybit_order_history = self.session.get_active_order(symbol=self.symbol,
                                                                order_status="Filled",
                                                                limit=50)['result']['data']
            order_history = []
            if bybit_order_history is not None:
                for bybit_order in bybit_order_history:
                    yyyy = int(bybit_order['created_time'][:4])
                    mm = int(bybit_order['created_time'][5:7])
                    dd = int(bybit_order['created_time'][8:10])
                    hh = int(bybit_order['created_time'][11:13])
                    mins = int(bybit_order['created_time'][14:16])
                    secs = int(bybit_order['created_time'][17:19])
                    timestamp = datetime.timestamp(datetime(yyyy, mm, dd, hh, mins, secs))
                    order_history.append([bybit_order['created_time'],
                                          timestamp,
                                          'Market',
                                          bybit_order['cum_exec_qty'],
                                          bybit_order['side'],
                                          bybit_order['last_exec_price'],
                                          bybit_order['stop_loss'],
                                          bybit_order['take_profit'],
                                          bybit_order['reduce_only']
                                          ])
            if bybit_conditional_order_history is not None:
                for conditional_order in bybit_conditional_order_history:
                    if conditional_order['order_status'] == 'Filled':
                        yyyy = int(conditional_order['updated_time'][:4])
                        mm = int(conditional_order['updated_time'][5:7])
                        dd = int(conditional_order['updated_time'][8:10])
                        hh = int(conditional_order['updated_time'][11:13])
                        mins = int(conditional_order['updated_time'][14:16])
                        secs = int(conditional_order['updated_time'][17:19])
                        timestamp = datetime.timestamp(datetime(yyyy, mm, dd, hh, mins, secs))
                        order_history.append([conditional_order['updated_time'],
                                              timestamp,
                                              'Conditional',
                                              conditional_order['qty'],
                                              conditional_order['side'],
                                              conditional_order['trigger_price'],
                                              conditional_order['base_price'],
                                              0.0,
                                              True
                                              ])

        except pybit.exceptions.FailedRequestError as ex:
            self.write_error_log(ex)
            order_history = []
        except pybit.exceptions.InvalidRequestError as ex:
            self.write_error_log(ex)
            order_history = []
        except requests.exceptions.Timeout as ex:
            self.write_error_log(ex)
            order_history = []
        except requests.exceptions.ConnectionError as ex:
            self.write_error_log(ex)
            order_history = []
        order_history.sort(key=lambda orders: orders[0])
        order_history.reverse()
        return order_history[:min(lim, len(order_history))]

    def get_trading_pairs(self, no=1):
        trading_pairs = []
        trades_found = 0
        order_no = 0
        trading_pair = []
        orders = self.get_order_history()
        while trades_found < no:
            if len(trading_pair) == 0 and orders[order_no][8]:
                trading_pair.append(orders[order_no])
                order_no += 1
            elif len(trading_pair) > 0 and not orders[order_no][8]:
                trading_pair.append(orders[order_no])
                order_no += 1
            elif len(trading_pair) > 0 and orders[order_no][8]:
                trading_pairs.append(trading_pair)
                trading_pair = []
                trades_found += 1
        return trading_pairs

    def get_closed_position_history(self, pairs=10):
        evaluated_pairs = []
        trading_pairs = self.get_trading_pairs(pairs)
        for trading_pair in trading_pairs:
            open_price = []
            size = []
            sl = trading_pair[1][6]
            tp = trading_pair[1][7]
            open_time = trading_pair[-1][0]
            close_time = trading_pair[0][0]
            for i in range(len(trading_pair) - 1):
                open_price.append(trading_pair[i + 1][5])
                size.append(trading_pair[i + 1][3])
            close_price = trading_pair[0][5]
            qty = trading_pair[0][3]
            if close_price == sl:
                reason = 'stop loss'
            elif close_price == tp:
                reason = 'take profit'
            else:
                reason = 'trigger'
            if trading_pair[1][4] == 'Buy':
                side = 'Long'
                win_rate = 0
                for i in range(len(open_price)):
                    win_rate += (size[i] / sum(size)) * (close_price / open_price[i] - 1) * config.leverage * 100
                win_rate = round(win_rate, 2)
            else:
                side = 'Short'
                win_rate = 0
                for i in range(len(open_price)):
                    win_rate += (size[i] / sum(size)) * (1 - close_price / open_price[i]) * config.leverage * 100
                win_rate = round(win_rate, 2)
            avg_open_price = round(sum(open_price) / len(open_price), 1)
            evaluated_pairs.append(
                [side, qty, open_time, avg_open_price, close_time, close_price, win_rate, reason, sl, tp])
        return evaluated_pairs

    # --- Set Exchange interaction methods ---
    def set_leverage(self):
        try:
            self.session.cross_isolated_margin_switch(symbol=self.symbol,
                                                      is_isolated=True,
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
        write_str = str(datetime.utcnow()) + '\n'
        self.set_leverage()
        with open('debug_trading_log.dat', 'a') as f:
            wallet_usd = self.get_wallet()
            write_str += 'wallet: ' + str(wallet_usd) + ' USD \n'
            current_price = self.get_price()
            write_str += 'current price: ' + str(current_price) + ' USD at ' + str(datetime.utcnow()) + ' (UTC) \n'
            order_amount = round(config.order_amount * wallet_usd / current_price * config.leverage, 5)
            write_str += 'order amount (usd): ' + str(config.order_amount * wallet_usd) + ' USD \n'
            write_str += 'order amount (btc): ' + str(order_amount) + ' BTC \n'
            if side == 'Long':
                side = "Buy"
                write_str += 'Position type: Long \n'
            elif side == 'Short':
                side = "Sell"
                write_str += 'Position type: Short \n'
            if side == "Buy":
                sl = int(round(current_price * (1 - config.stop_loss / config.leverage), 1))
                tp = int(round(current_price * (1 + config.take_profit), 1))
            elif side == "Sell":
                sl = int(round(current_price * (1 + config.stop_loss / config.leverage), 1))
                tp = int(round(current_price * (1 - config.take_profit), 1))
            else:
                sl = 0
                tp = 0
            write_str += 'TP: ' + str(tp) + ' USD \n'
            write_str += 'SL: ' + str(sl) + ' USD \n'
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
            pos = self.get_position(time.time())
            write_str += 'Position open price: ' + str(pos[1]) + ' USD at ' + str(datetime.utcnow()) + ' (UTC) \n'
            self.positions.append(pos)
            self.write_trade_log('open', pos, '')
            write_str += '-----------------------------------------------'
            f.write(write_str)
            f.close()
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
            self.write_trade_log('close', pos, 'trigger')
            self.trade_history.append(pos)
            self.write_trade_history_log(pos)
            self.positions.pop(0)

    # --- Data processing methods ---
    def add_new_dataframe(self):
        now = datetime.utcnow()
        unix_time = calendar.timegm(now.utctimetuple())
        since = unix_time - self.time_frame * 2 * 60
        new_df = self.get_dataframe(since, 2, config.timeframe)
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
                print(self.candle_to_string(-2), flush=True)
                self.write_to_log(self.candle_to_string(-2))
                self.write_to_log(self.indicators_to_string())
                print(self.indicators_to_string(), flush=True)

    def read_historical_data(self):
        if config.symbol == 'BTCUSDT':
            date_tuple = (2018, 12, 1)
        elif config.symbol == 'ATOMUSDT':
            date_tuple = (2021, 10, 12)
        else:
            date_tuple = (2022, 1, 1)
        self.df = self.get_history_dataframes(date_tuple[0], date_tuple[1], date_tuple[2])
        self.df, offset = self.strategy.populate_indicators(self.df)

    def validate_positions(self):
        if len(self.previous_positions) > len(self.positions):
            time.sleep(15)
            closed_position = self.get_closed_position_history(1)[0]
            closed_position[7] = 'hand (manually)'
            if len(closed_position) > 0:
                yyyy = int(closed_position[2][:4])
                mm = int(closed_position[2][5:7])
                dd = int(closed_position[2][8:10])
                hh = int(closed_position[2][11:13])
                mins = int(closed_position[2][14:16])
                secs = int(closed_position[2][17:19])
                timestamp = datetime.timestamp(datetime(yyyy, mm, dd, hh, mins, secs))
                position = [timestamp, closed_position[3], closed_position[1], closed_position[0], config.leverage,
                            closed_position[8], closed_position[9], closed_position[5], closed_position[6],
                            round(closed_position[1]*closed_position[6]/100, 8)]

                self.write_trade_log('close', position, closed_position[7])
                self.trade_history.append(position)
                self.write_trade_history_log(position)
        else:
            send_str = 'The following position has been opened manually: \n' + self.active_position_to_string()
            print(send_str)
            self.write_to_log(send_str)
            if config.enable_telegram:
                self.send_telegram_msg(send_str)

    def adjust_stop_loss(self):
        # [5] stop_loss: stop loss
        # [6] take_profit: take profit
        pos = self.get_position(0)
        if len(pos) > 0:
            price = self.get_price()
            if pos[3] == 'Long':
                if (price / pos[1] - 1) > 0.03 and pos[5] < pos[1]:
                    new_sl = round((1 + 0.005) * pos[1], 1)
                    write_str = str(datetime.utcnow()) + ': Price reached ' + str(price) + ' USD. \n ' \
                                + 'Entry price of Long position:' + str(pos[1]) + ' USD. \n ' \
                                + 'Adjusted stop loss from ' + str(pos[5]) + ' USD to: ' + str(new_sl) + ' USD.'
                    print(write_str, flush=True)
                    self.write_to_log(write_str)
                    self.set_stop_loss(new_sl, 'Buy')
                    self.positions[self.positions.index(pos)][5] = new_sl
                    if config.enable_telegram:
                        self.send_telegram_msg(write_str)
            elif pos[3] == 'Short':
                if (1 - (price / pos[1])) > 0.03 and pos[5] > pos[1]:
                    new_sl = round((1 - 0.005) * pos[1], 1)
                    write_str = str(datetime.utcnow()) + ': Price reached ' + str(price) + ' USD. \n ' \
                                + 'Entry price of Short position:' + str(pos[1]) + ' USD. \n ' \
                                + 'Adjusted stop loss from ' + str(pos[5]) + ' USD to: ' + str(new_sl) + ' USD.'
                    print(write_str, flush=True)
                    self.write_to_log(write_str)
                    self.set_stop_loss(new_sl, 'Sell')
                    self.positions[self.positions.index(pos)][5] = new_sl
                    if config.enable_telegram:
                        self.send_telegram_msg(write_str)

    def validate_bot_running(self):
        candle_validation = [0.0]*10
        while True:
            candle_validation.pop(0)
            candle_validation.append(float(self.df['volume'].iloc[-1]))
            validation_counter = 0
            for i in range(len(candle_validation)):
                if candle_validation[0] == candle_validation[i]:
                    validation_counter += 1
            if validation_counter == len(candle_validation) and not self.warning_sent:
                self.send_telegram_msg(str(datetime.utcnow()) + '(UTC): the volume has not changed during'
                                                                ' the 10 latest requests. Please check if the bot'
                                                                ' is still running properly.')
                self.warning_sent = True
            time.sleep(config.dt)

    def request_command(self):
        if len(sys.argv) > 1:
            command = sys.argv[1]
        else:
            command = input('Enter command ['
                            '0: run backtest \t '
                            '1: start trading loop (active) \t '
                            '2: start trading loop (passive) \t '
                            '3: exit program]: \n')
        try:
            command = int(command)
        except ValueError:
            command = None
        if command == 0:
            delta_time = self.backtest_enter_start_time()
            self.backtest(delta_time)
            self.request_command()
        elif command == 1:
            self.trading_enabled = True
            print('enabled active trading. \n', flush=True)
        elif command == 2:
            self.trading_enabled = False
            print('disabled active trading. \n', flush=True)
        elif command == 3:
            print('Exiting program...', flush=True)
            sys.exit()
        else:
            print('Error: invalid input. Try again... \n', flush=True)
            self.request_command()

    # --- Write and print methods ---
    def write_error_log(self, ex):
        write_str = str(datetime.utcnow()) + ': ' + str(ex)
        print(write_str)
        with open(self.error_log, 'a', encoding='utf-8') as f:
            f.write(write_str + '\n')
            f.close()

    def write_to_log(self, msg):
        with open(self.log, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
            f.close()

    def write_trade_log(self, side, position, reason):
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
                            str(position[7]) + ' USD by ' + reason + '. Entry price: ' + str(position[1]) + \
                            ' USD. Trade closed with win rate: ' + str(position[8]) + '% and an absolute win of: ' +\
                            str(position[9]) + ' BTC.' + '(TP: ' + str(position[6]) + ' SL:' + str(position[5]) + ')'
            elif side == 'open':
                write_str = str(datetime.utcnow()) + ': Opened a new ' + str(position[3]) + ' position at ' \
                            + str(position[1]) + 'USD. Stop loss: ' + str(position[5]) + ' USD. Take profit: ' \
                            + str(position[6]) + 'USD. Position size: ' + str(position[2])
            with open(self.trade_log, 'a') as f:
                f.write(write_str + '\n')
                f.close()
            if config.enable_telegram:
                self.send_telegram_msg(write_str)
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
                        str(position[9]) + ' BTC.'
            with open(self.trade_history_log, 'a') as f:
                f.write(write_str + '\n')
                f.close()

    def start_message(self):
        start_msg = str(datetime.utcnow()) + ': Starting bot trading loop:'
        print(str(datetime.utcnow()) + ': Wallet balance:' + str(self.get_wallet()) + ' USDT', flush=True)
        print(self.active_position_to_string())
        candle_report = self.candle_to_string(-2)
        print(start_msg, flush=True)
        print(candle_report, flush=True)
        if config.enable_telegram:
            self.send_telegram_msg(start_msg)
            self.send_telegram_msg(candle_report)

    # --- Information to string conversion ---
    def active_position_to_string(self):
        result = ''
        if len(self.positions) == 0:
            result = str(datetime.utcnow()) + ': Currently, there are no active positions. \n'
        else:
            for position in self.positions:
                result = str(datetime.utcnow()) + ': Side: ' + str(position[3]) + '. Size: ' + str(position[2]) + \
                         ' BTC. Entry price: ' + str(position[1]) + ' BTCUSD. Leverage: ' + str(position[4]) + \
                         '. Stop loss: ' + str(position[5]) + ' USD. Take profit: ' + str(position[6]) + ' USD.'
        return result

    def candle_to_string(self, pos):
        write_str = ''
        # candle_keys = ['open_time', 'symbol', 'period']
        for key in self.candle_keys:
            if key in ['volume', 'open', 'high', 'low', 'close']:
                write_str += str(key) + ': ' + str(self.df[key].iloc[pos]) + ' USD, \n'
            elif key in ['period']:
                write_str += str(key) + ': ' + str(self.df[key].iloc[pos]) + ' min, \n'
            elif key == 'open_time':
                open_time = datetime.utcfromtimestamp(int(self.df[key].iloc[pos]))
                write_str += str(key) + ': ' + str(open_time) + ' (UTC), \n'
            else:
                write_str += str(key) + ': ' + str(self.df[key].iloc[pos]) + ', \n'
        write_str += 'K: ' + str(self.df['K'].iloc[pos])
        return write_str

    def indicators_to_string(self):
        write_str = ''
        for key in self.indicators:
            write_str += ' - ' + str(key) + ': ' + str(self.df[key].iloc[-1])
        return write_str

    # --- Backtest methods ---
    def convert_backtest_starting_time(self, t):
        start_date = datetime.now()
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
        start_date += dt.timedelta(days=-1 * time_quantity * delta_t)
        trash, offset = self.strategy.populate_indicators(pd.DataFrame())
        start_date += dt.timedelta(minutes=-1 * self.time_frame * offset)
        return start_date

    def backtest(self, t):
        importlib.reload(config)
        importlib.reload(kdj_strategy)
        self.positions = []
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

        start_date = self.convert_backtest_starting_time(t)
        timestamp = calendar.timegm(dt.datetime(start_date.year, start_date.month, start_date.day).utctimetuple())
        df = self.get_dataframe(timestamp, 200, config.timeframe)
        if timestamp != df['open_time'][0]:
            print('Unable to start backtest at: ' + str(start_date.year) + '-' + str(start_date.month) + '-' +
                  str(start_date.day) + '. No available data at that time.', flush=True)
            start_date = datetime.utcfromtimestamp(df['open_time'][0])
            print('First available data starts at: ' + str(start_date.year) + '-' + str(start_date.month) + '-' +
                  str(start_date.day) + '. Using this date as start point.')
        else:
            start_date = self.convert_backtest_starting_time(t)

        filename = 'Backtest' + str(time.time()) + '.dat'
        write_str = 'Starting backtest for Pair ' + config.symbol + ' from ' + str(start_date.year) + '-' +\
                    str(start_date.month) + '-' + str(start_date.day) + ', time frame: ' + str(config.timeframe) + '...'
        print(write_str)
        with open(filename, 'w') as f:
            f.write(write_str)
            f.close()

        self.df = self.get_history_dataframes(start_date.year, start_date.month, start_date.day)
        # Loading strategy
        print(str(datetime.utcnow()) + ': Loading strategy', flush=True)
        self.df, offset = self.strategy.populate_indicators(self.df)

        # Running backtest
        print(str(datetime.utcnow()) + ': Running backtest \n ...', flush=True)
        n = range(offset, len(self.df), 1)
        for i in n:
            # adjust stop loss
            self.adjust_backtest_stop_loss(i, filename)

            # check triggers
            self.trigger = self.strategy.populate_trigger(self.df.iloc[0:i])

            if 'close_short' in self.trigger:
                for position in self.positions:
                    if position[3] == 'Short':
                        win_rate = self.close_backtest_order(self.df['open'][i-1], 'trigger',
                                                             self.df['open_time'][i-1], filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        tr_counter += 1
            if 'close_long' in self.trigger:
                for position in self.positions:
                    if position[3] == 'Long':
                        win_rate = self.close_backtest_order(self.df['open'][i-1], 'trigger',
                                                             self.df['open_time'][i-1], filename)
                        flat_win_rate += win_rate*config.order_amount
                        wallet += wallet*config.order_amount*win_rate
                        tr_counter += 1

            # place a new order
            if 'open_long' in self.trigger and len(self.positions) < self.max_open_trades:
                position = self.place_backtest_order(self.df['open_time'][i-1], self.df['open'][i-1],
                                                     wallet, 'Long')
                self.positions.append(position)
                write_str = '\n' + str(datetime.utcfromtimestamp(position[0])) + ': Open ' + position[3] + \
                            ' position at ' + str(position[1]) + ' USD with SL at ' + str(round(position[5], 2)) + \
                            ' USD and TP at ' + str(round(position[6], 2)) + ' USD. Order amount: ' + \
                            str(round(position[2], 2)) + ' USD and leverage: ' + str(position[4])
                with open(filename, 'a') as f:
                    f.write(write_str)
                trade_counter += 1
            elif 'open_short' in self.trigger and len(self.positions) < self.max_open_trades:
                position = self.place_backtest_order(self.df['open_time'][i-1], self.df['open'][i-1],
                                                     wallet, 'Short')
                self.positions.append(position)
                write_str = '\n' + str(datetime.utcfromtimestamp(position[0])) + ': Open ' + position[3] + \
                            ' position at ' + str(position[1]) + ' USD with SL at ' + str(round(position[5], 2)) + \
                            ' USD and TP at ' + str(round(position[6], 2)) + ' USD. Order amount: ' + \
                            str(round(position[2], 2)) + ' USD and leverage: ' + str(position[4])
                with open(filename, 'a') as f:
                    f.write(write_str)
                trade_counter += 1

            # check stop loss and take profit
            wallet, sl_counter, tp_counter, flat_win_rate = self.backtest_check_sl_tp(i, wallet, sl_counter,
                                                                                      tp_counter, flat_win_rate,
                                                                                      filename)
        write_str = str(datetime.utcnow()) + ': Backtest done. \n ' + str(trade_counter) + \
                    ' trades have been made with total ' + str(round((wallet-1)*100, 2)) + \
                    '% win-rate. \n The trades were canceled ' + str(sl_counter) + \
                    ' times by stop loss, ' + str(tp_counter) + ' times by take profit and ' + str(tr_counter) + \
                    ' times by trigger threshold. \n The flat win rate would have been: ' + \
                    str(round(flat_win_rate*100, 2)) + '%'
        print(write_str, flush=True)
        with open(filename, 'a') as f:
            f.write(write_str)
            f.close()
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

            axs[1].plot(dates_list, self.df['K'], 'b',
                        dates_list, self.df['boll_upper'], 'r',
                        dates_list, self.df['boll_lower'], 'g')
            axs[1].grid(b=True, which='major', color='k', linestyle='-')
            axs[1].grid(b=True, which='minor', color='k', linestyle='--')
            axs[1].set_xlim(dates_list[0], dates_list[len(dates_list)-1])
            plt.show()

    def backtest_check_sl_tp(self, df_counter, wallet, sl_counter, tp_counter, flat_win_rate, filename):
        for position in self.positions:
            if position[3] == 'Short':
                if self.df['low'][df_counter - 1] <= position[6]:
                    win_rate = self.close_backtest_order(position[6],
                                                         'take profit',
                                                         self.df['open_time'][df_counter - 1],
                                                         filename)
                    flat_win_rate += win_rate * config.order_amount
                    wallet += wallet * config.order_amount * win_rate
                    tp_counter += 1
                elif self.df['high'][df_counter - 1] >= position[5]:
                    win_rate = self.close_backtest_order(position[5],
                                                         'stop loss',
                                                         self.df['open_time'][df_counter - 1],
                                                         filename)
                    flat_win_rate += win_rate * config.order_amount
                    wallet += wallet * config.order_amount * win_rate
                    sl_counter += 1
            elif position[3] == 'Long':
                if self.df['high'][df_counter - 1] >= position[6]:
                    win_rate = self.close_backtest_order(position[6],
                                                         'take profit',
                                                         self.df['open_time'][df_counter - 1],
                                                         filename)
                    flat_win_rate += win_rate * config.order_amount
                    wallet += wallet * config.order_amount * win_rate
                    tp_counter += 1
                elif self.df['low'][df_counter - 1] <= position[5]:
                    win_rate = self.close_backtest_order(position[5],
                                                         'stop loss',
                                                         self.df['open_time'][df_counter - 1],
                                                         filename)
                    flat_win_rate += win_rate * config.order_amount
                    wallet += wallet * config.order_amount * win_rate
                    sl_counter += 1
        return wallet, sl_counter, tp_counter, flat_win_rate

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
            write_str = '\n' + str(datetime.utcfromtimestamp(close_time)) + ': Close ' + str(position[3]) + \
                        ' position at: ' + str(round(close_price, 1)) + ' USD/BTC by ' + reason + '. Order amount: ' + \
                        str(round(position[2], 2)) + ' with leverage: ' + str(position[4]) + '. Win-rate: ' + \
                        str(round(profit * 100, 2)) + '%.'
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

    def adjust_backtest_stop_loss(self, it, log_file):
        for position in self.positions:
            if position[3] == 'Short':
                price = self.df['low'][it-1]
                if (1 - (price / position[1])) > 0.03 and position[5] > position[1]:
                    new_sl = round((1 - 0.005) * position[1], 1)
                    old_sl = round(self.positions[0][5], 1)
                    self.positions[0][5] = new_sl
                    write_str = '\n' + str(datetime.utcfromtimestamp(self.df['open_time'][it-1])) +\
                                ': changed stop loss from ' + str(old_sl) + ' USD to ' + str(new_sl)
                    with open(log_file, 'a') as f:
                        f.write(write_str)
                        f.close()
            if position[3] == 'Long':
                price = self.df['high'][it-1]
                if (price / position[1] - 1) > 0.03 and position[5] < position[1]:
                    new_sl = round((1 + 0.005) * position[1], 1)
                    old_sl = round(self.positions[0][5], 1)
                    self.positions[0][5] = new_sl
                    write_str = '\n' + str(datetime.utcfromtimestamp(self.df['open_time'][it-1])) +\
                                ': changed stop loss from ' + str(old_sl) + ' USD to ' + str(new_sl)
                    with open(log_file, 'a') as f:
                        f.write(write_str)
                        f.close()

    def backtest_enter_start_time(self):
        delta_time = input(
            'Enter the duration of the backtest (e.g. "2W" for two weeks or "3M" for three months): \n')

        if delta_time[-1] not in ['D', 'W', 'M', 'Y'] or not delta_time[0:-1].isnumeric():
            print('Error: invalid time rage.', flush=True)
            print('valid input consists of a number and a time unit (D, W, M, Y). E.g. "2W", "1Y", "19D"', flush=True)
            print('Please try again...', flush=True)
            delta_time = self.backtest_enter_start_time()
        return delta_time

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

    # --- Telegram methods ---
    def send_telegram_msg(self, msg):
        msg_sent = False
        response = None
        msg = msg.replace('_', '-')
        send_text = 'https://api.telegram.org/bot' + config.telegram_token + '/sendMessage?chat_id=' + \
                    config.telegram_chatID + '&parse_mode=Markdown&text=' + msg
        while not msg_sent:
            try:
                response = requests.get(send_text)
                msg_sent = True
            except requests.exceptions.ConnectionError as ex:
                response = None
                self.write_error_log(ex)
            except requests.exceptions.ReadTimeout as ex:
                response = None
                self.write_error_log(ex)
            except requests.exceptions.Timeout as ex:
                response = None
                self.write_error_log(ex)
        return response.json()

    def setup_telegram_bot(self, timer=0):
        updater = Updater(config.telegram_token, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler(self.tel_commands[0], self.tel_start_trading_command))
        dp.add_handler(CommandHandler(self.tel_commands[1], self.tel_stop_trading_command))
        dp.add_handler(CommandHandler(self.tel_commands[2], self.tel_help_command))
        dp.add_handler(CommandHandler(self.tel_commands[3], self.tel_status_command))
        dp.add_handler(CommandHandler(self.tel_commands[4], self.tel_position_command))
        dp.add_handler(CommandHandler(self.tel_commands[5], self.tel_candle_command))
        dp.add_handler(CommandHandler(self.tel_commands[6], self.tel_trade_history_command))
        dp.add_handler(CommandHandler(self.tel_commands[7], self.tel_close_position))
        dp.add_handler(CommandHandler(self.tel_commands[8], self.tel_reset_warning))
        dp.add_error_handler(self.tel_error)
        dp.add_handler(MessageHandler(Filters.text, self.tel_handle_message))
        updater.start_polling(poll_interval=timer, timeout=600)

    def tel_start_trading_command(self, update, context):
        update.message.reply_text("Enabling trading mode")
        self.trading_enabled = True

    def tel_stop_trading_command(self, update, context):
        update.message.reply_text("Disabling trading mode")
        self.trading_enabled = False

    def tel_help_command(self, update, context):
        tel_description = ["enables trading mode",
                           "disables trading mode",
                           "prints help information",
                           "prints current status (wallet size, positions, trading status)",
                           "prints currently open positions",
                           "prints the latest closed candle and the current candle",
                           "prints trade history of the past 10 trades",
                           "closes an open position",
                           "resets the bot crash warning"]
        send_str = "You can use one of the following commands: \n"
        for i in range(len(self.tel_commands)):
            send_str += self.tel_commands[i] + " : "
            send_str += tel_description[i] + "\n"
        update.message.reply_text(send_str)

    def tel_status_command(self, update, context):
        send_str = ''
        if self.trading_enabled:
            send_str += 'Active trading is enabled. \n'
        else:
            send_str += 'Active trading is disabled. \n'
        send_str += 'Wallet size: ' + str(self.get_wallet()) + ' USDT \n'
        update.message.reply_text(send_str)
        self.tel_position_command(update, context)

    def tel_position_command(self, update, context):
        pos = self.get_position(0)
        if len(pos) > 0:
            price = self.get_price()
            if pos[3] == 'Long':
                win_rate = round((price / pos[1] - 1) * 100 * pos[4], 2)
            else:
                win_rate = round((1 - price / pos[1]) * 100 * pos[4], 2)
            send_str = 'Position type: ' + str(pos[3]) + '\n' + \
                       'Position size: ' + str(pos[2]) + ' BTC \n' + \
                       'Open price: ' + str(pos[1]) + ' BTCUSD \n' + \
                       'Leverage: ' + str(pos[4]) + '\n' + \
                       'Take profit: ' + str(pos[6]) + ' USD \n' + \
                       'Stop loss: ' + str(pos[5]) + ' USD \n' + \
                       'Current price: ' + str(price) + ' USD \n' + \
                       'Current win rate: ' + str(win_rate) + ' %'
        else:
            send_str = 'Currently no open positions.'
        update.message.reply_text(send_str)

    def tel_candle_command(self, update, context):
        send_str = str(datetime.utcnow()) + ': \n'
        send_str += 'Latest closed candle: \n'
        send_str += self.candle_to_string(-2) + '\n'
        send_str += 'Current candle: \n'
        send_str += self.candle_to_string(-1)
        update.message.reply_text(send_str)

    def tel_trade_history_command(self, update, context):
        position_history = self.get_closed_position_history(10)
        n = len(position_history)
        if n > 0:
            send_str = 'The ' + str(n) + ' latest trades: \n'
            nr = 1
            for position in position_history:
                send_str += str(nr) + ': ' + str(position[0]) + ' position closed at ' + str(position[4]) + ' at ' + \
                            str(position[5]) + ' by ' + str(position[7]) + '. Win rate: ' + str(position[6]) + '% \n'
                nr += 1
        else:
            send_str = 'No trades found in your trading history.'
        update.message.reply_text(send_str)

    def tel_close_position(self, update, context):
        send_str = 'Call: close position:\n'
        pos = self.get_position(0)
        if len(pos) > 0:
            price = self.get_price()
            if pos[3] == 'Long':
                win_rate = round((price / pos[1] - 1) * 100 * pos[4], 2)
            else:
                win_rate = round((1 - price / pos[1]) * 100 * pos[4], 2)
            send_str += 'Position type: ' + str(pos[3]) + '\n' + \
                        'Position size: ' + str(pos[2]) + ' BTC \n' + \
                        'Open price: ' + str(pos[1]) + ' BTCUSD \n' + \
                        'Leverage: ' + str(pos[4]) + '\n' + \
                        'Take profit: ' + str(pos[6]) + ' USD \n' + \
                        'Stop loss: ' + str(pos[5]) + ' USD \n' + \
                        'Current price: ' + str(price) + ' USD \n' + \
                        'Current win rate: ' + str(win_rate) + ' %'
            closed_pos = True
        else:
            send_str += 'Currently no open positions.'
            closed_pos = False
        self.send_telegram_msg(send_str)
        self.close_active_position()
        if closed_pos:
            send_str = 'Position has been closed'
        else:
            send_str = 'There was no position to close'
        update.message.reply_text(send_str)

    def tel_reset_warning(self, update, context):
        send_str = 'call: reset warning:'
        self.send_telegram_msg(send_str)
        self.warning_sent = False
        send_str = 'warning thread was set to active'
        update.message.reply_text(send_str)

    def tel_handle_message(self, update, context):
        text = str(update.message.text).lower()
        if text in ("candle", "update"):
            send_str = self.candle_to_string(-2)
        elif text in ("hello", "hi", "sup"):
            send_str = "Hey! How's it going?"
        else:
            send_str = "I don't understand you!"
        self.send_telegram_msg(send_str)

    @staticmethod
    def tel_error(update, context):
        print(f"Update {update} caused error {context.error}")

    @staticmethod
    def tel_sample_response(input_text):
        user_message = str(input_text).lower()
        # position, daily report, status
        if user_message in ("hello", "hi", "sup"):
            return "Hey! How's it going?"
        return "I don't understand you!"

# ToDo: not urgent - evaluate trading pairs by delta_position_size = 0 and not by reduce_only==True
