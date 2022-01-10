api_key = ""
api_secret = ""

symbol = "BTCUSDT"          # trading pair
order_amount = 0.75         # percentage of the available balance for one order
leverage = 3                # leverage for trading
max_open_trades = 1         # number of trades that are open at the same time
stop_loss = 0.1             # stop loss in [%]
take_profit = 0.15          # take profit in [%]
mode = "live-run"           # sets the trading bot mode: "live-run", "dry-run", "backtest"
dt = 5                      # time between two candle-requests [s]
timeframe = 240             # Time Frames: [1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, D, W, M] -> to minutes 4h=240min

strategy = "kdj_strategy"   # strategy .py file name
enable_dynamic_sl = True    # enables dynamic stop loss modification

plot = False                 # shows backtest plots

# Log-File Configurations
output_indicator = True     # Defines if current indicators are printed
log_indicator = True        # Defines if current indicators are exported to Log-File
log_file = 'log_file.dat'               # Log-File
trade_file = 'trade_log.dat'            # Trading Log-File
trade_hist_file = 'trade_history.dat'   # Trading history File
backtest_file = 'backtest_log.dat'      # Backtest Log-File
error_file = 'error_log.dat'            # Error Log-File

# Telegram configuration
enable_telegram = False
telegram_token = ''
telegram_chatID = ''
