
import calendar
import datetime as dt
import crypto_bot
import importlib
import config
strategy = importlib.import_module(config.strategy)


bot = crypto_bot.Bot()

bot.read_historical_data()

timer = calendar.timegm(dt.datetime.utcnow().utctimetuple()) - config.dt
print(str(dt.datetime.utcnow()) + ': Bot setup done. Start running...', flush=True)
while True:
    if abs(calendar.timegm(dt.datetime.utcnow().utctimetuple()) - timer) > config.dt:
        timer = calendar.timegm(dt.datetime.utcnow().utctimetuple())

        # -------------- populate candles --------------
        bot.add_new_dataframe()

        # -------------- Populate Triggers --------------
        bot.trigger = bot.strategy.populate_trigger(bot.df)

        # -------------- Processing Live Run --------------
        if bot.trading_mode == "live-run":

            # -------------- Check TP and SL criteria  --------------
            if len(bot.positions) > 0 and len(bot.get_position(0)) == 0:
                bot.validate_sl_tp()

            # -------------- Check dynamic stop loss  --------------
            if config.enable_dynamic_sl and len(bot.positions) > 0:
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
