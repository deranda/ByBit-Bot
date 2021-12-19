# ToDo: - evaluate test-mode with live "k" values sent via telegram
import calendar
import datetime as dt
import crypto_bot
import importlib
import config
from datetime import datetime
strategy = importlib.import_module(config.strategy)


bot = crypto_bot.Bot()

bot.read_historical_data()

triggered_buy = False
triggered_sell = False
timer = calendar.timegm(dt.datetime.utcnow().utctimetuple()) - config.dt
bot.start_message()
while True:
    if abs(calendar.timegm(dt.datetime.utcnow().utctimetuple()) - timer) > config.dt:
        timer = calendar.timegm(dt.datetime.utcnow().utctimetuple())
        # -------------- populate candles --------------
        bot.add_new_dataframe()

        # -------------- Populate Triggers --------------
        bot.trigger = bot.strategy.populate_trigger(bot.df)
        if not triggered_buy:
            if bot.df['K'].iloc[-1] <= 27:
                write_str = str(datetime.utcnow()) + ': Buy-Live triggered with K=' + str(bot.df['K'].iloc[-1]) + \
                            '. Price=' + str(bot.df['close'].iloc[-1]) + ' USDT. \n'
                print(write_str, flush=True)
                bot.send_telegram_msg(write_str)
                triggered_buy = True
                triggered_sell = False
        if not triggered_sell:
            if bot.df['K'].iloc[-1] > 75:
                write_str = str(datetime.utcnow()) + ': Sell-Live triggered with K=' + str(bot.df['K'].iloc[-1]) + \
                            '. Price=' + str(bot.df['close'].iloc[-1]) + ' USDT. \n'
                print(write_str, flush=True)
                bot.send_telegram_msg(write_str)
                triggered_sell = True
                triggered_buy = False

        # -------------- Processing Live Run --------------
        if bot.trading_enabled:

            # -------------- Check TP and SL criteria  --------------
            if len(bot.positions) != len(bot.get_position(0)):
                print(str(datetime.now()) + ': validating positions:')
                bot.validate_positions()

            # -------------- Check dynamic stop loss  --------------
            if config.enable_dynamic_sl:
                bot.adjust_stop_loss()

            # -------------- Check indicator trigger criteria  --------------
            if bot.trigger == 'Long':
                if len(bot.positions) > 0 and bot.positions[0][3] == 'Short':
                    bot.close_active_position()
                if len(bot.positions) < bot.max_open_trades:
                    bot.place_order('Buy')

            elif bot.trigger == 'Short':
                if len(bot.positions) > 0 and bot.positions[0][3] == 'Long':
                    bot.close_active_position()
                if len(bot.positions) < bot.max_open_trades:
                    bot.place_order('Sell')
