# ToDo:
import calendar
import datetime as dt
import crypto_bot
import config
import threading

# -------------- creating bot object --------------
bot = crypto_bot.Bot()

bot.request_command()

bot.read_historical_data()

# -------------- start crash warning thread --------------
if config.enable_telegram:
    valid_thread = threading.Thread(target=bot.validate_bot_running, args=(), daemon=True)
    valid_thread.start()

timer = calendar.timegm(dt.datetime.utcnow().utctimetuple()) - config.dt
bot.start_message()
while True:
    if abs(calendar.timegm(dt.datetime.utcnow().utctimetuple()) - timer) > config.dt:
        timer = calendar.timegm(dt.datetime.utcnow().utctimetuple())
        # -------------- populate candles --------------
        bot.add_new_dataframe()

        # -------------- Populate Triggers --------------
        bot.trigger = bot.strategy.populate_trigger(bot.df)

        # -------------- Processing Live Run --------------
        if bot.trading_enabled:
            # -------------- Update positions  --------------
            bot.previous_positions = bot.positions
            new_position = bot.get_position(0)
            if len(new_position) > 0:
                bot.positions = [bot.get_position(0)]
            else:
                bot.positions = []
            # if len(bot.previous_positions) != len(bot.positions):
            #     bot.validate_positions()

            # -------------- Check dynamic stop loss  --------------
            if config.enable_dynamic_sl:
                bot.adjust_stop_loss()

            # -------------- Check indicator trigger criteria  --------------
            if 'close_long' in bot.trigger and len(bot.positions) > 0 and bot.positions[0][3] == 'Long' or\
               'close_short' in bot.trigger and len(bot.positions) > 0 and bot.positions[0][3] == 'Short':
                bot.close_active_position()
            if 'open_long' in bot.trigger and len(bot.positions) < bot.max_open_trades:
                bot.place_order('Buy')
            if 'open_short' in bot.trigger and len(bot.positions) < bot.max_open_trades:
                bot.place_order('Sell')
