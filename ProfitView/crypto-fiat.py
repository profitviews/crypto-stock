from profitview import Link, logger, cron, http
import time 
import os
import json
import builtins
import math
from my.venues import Venue, BitMEX, OANDA
from dotenv import load_dotenv

cron.options['auto_start'] = False

load_dotenv()


class Trading(Link):
	INTERVAL = 6000          # Time (seconds) between limit order resets
	VENUE = 'BitMEX'
	RUNGS = 5              
	MULT = .15               # Multiple of base increment to use between grids
	BASE_SIZE = 120        # In US$: minimum notional value of a contract (rounded down to lot value multiple)
	SIZE = 7               # Multiple of BASE_SIZE
	LIMIT = 15              # Multiple of BASE_SIZE
	QUOTE_DELAY = 2        # Time to wait initially for a first bid/ask quote
	RATE_LIMIT_DELAY = .1  
	
	OANDA_API_PRACTICE_URL = os.getenv("OANDA_API_PRACTICE_URL")
	OANDA_API_LIVE_URL = os.getenv("OANDA_API_LIVE_URL")
	OANDA_API_KEY = os.getenv("OANDA_API_KEY")
	OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
	OANDA_ENV = "practice"
	OANDA_STREAM_URL = (
    	f"wss://stream-fx{OANDA_ENV}.oanda.com/v3/accounts/{OANDA_ACCOUNT_ID}/pricing/stream?instruments=EUR_USD"
	)
	
	ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
	ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
	ALPACA_PAPER_API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
	ALPACA_PAPER_API_SECRET = os.getenv("ALPACA_PAPER_API_SECRET")
	
	symbol = 'XBTUSD'
	
	synthetics = {
		"XBTEUR": {"fx": "EUR_USD", "crypto": "XBTUSD"},	
		"XBTJPY": {"fx": "USD_JPY", "crypto": "XBTUSD"},	
		"XBTAUD": {"fx": "AUD_USD", "crypto": "XBTUSD"},	
		"XBTGBP": {"fx": "GBP_USD", "crypto": "XBTUSD"},
		"ETHEUR": {"fx": "EUR_USD", "crypto": "ETHUSD"},	
		"ETHGBP": {"fx": "GBP_USD", "crypto": "ETHUSD"}
	}
	
	quoted = False
	
    def on_start(self):
		time.sleep(self.QUOTE_DELAY)  # Wait for a first quote
		# Get parameters specific to this instrument
		if not self.venue_setup():
			logger.error(f"Error getting instrument data from venues - ending algo")
			raise RuntimeError()
		logger.info(f"Completed {self.VENUE} specific setup")
		logger.info(f"EUR_USD mark price: {self.fx_venue.mark_price('EUR_USD')}")
		logger.info(f"EUR_USD standard size: {self.fx_venue.standard_size('EUR_USD', 1000)}")
		logger.info(f"XBTUSD mark price: {self.crypto_venue.mark_price('XBTUSD')}")
		logger.info(f"XBTUSD standard size: {self.crypto_venue.standard_size('XBTUSD', 1000)}")
		cron.start(run_now=True)

	def venue_setup(self):
		try:
			self.fx_venue = OANDA(self, self.OANDA_ACCOUNT_ID, self.OANDA_API_KEY, endpoint=self.OANDA_API_PRACTICE_URL)
			self.crypto_venue = BitMEX(self)
			logger.info("Venues set up")
			return True
		except Exception as ex:
			logger.info(f"Couldn't set up all venues. Exception: {ex}")
			return False
	
	def get_lot_size(self, symbol):
		synthetic = self.synthetics[symbol]
		lot_size = math.lcm(self.fx_venue.lot(synthetic['fx']), self.crypto_venue.lot(synthetic['crypto']))
		logger.info(f"{symbol} lot size = {lot_size}")
		return lot_size
			
	def place_market_order(self, symbol, side, quantity):
		side = side.lower()
		if synthetic := self.synthetics.get(symbol):
			if quantity % self.get_lot_size(symbol) == 0:
				fx_side = "buy" if side == "sell" else "sell"
				self.fx_venue.place_order(synthetic['fx'], fx_side, quantity)  # quantity must be corrected
				self.crypto_venue.place_order(synthetic['crypto'], side, quantity)  # quantity must be corrected

	@cron.run(every=INTERVAL)
	def update_signal(self):
		"""Do stuff"""
		pass
	
	@http.route
	def get_lot(self, data):
		logger.info(f"Data: {data=}")
		return self.get_lot_size(data['symbol'])

	@http.route
	def get_market_order(self, data):
		logger.info(f"Data: {data=}")
		self.place_market_order(data['symbol'], data['side'], int(data['quantity']))
		return "Placed market order"


def round_to(value, increment):
	"""Round `value` to an exact multiple of `increment`"""
	return round(value/increment)*increment
