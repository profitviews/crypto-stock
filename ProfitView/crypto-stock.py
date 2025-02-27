from profitview import Link, logger, http
import os
import json
import math

# See venues.py in the repo. 
# I've chosen to put the code in the `my` directory under `src` in the container
from my.venues import BitMEX, Alpaca
from dotenv import load_dotenv


load_dotenv()


class Trading(Link):
	ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
	ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
	ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL")
	ALPACA_ENV = "paper"
			
    def on_start(self):
		if not self.venue_setup():
			logger.error(f"Error getting instrument data from venues - ending algo")
			raise RuntimeError()

	def venue_setup(self):
		try:
			self.stock_venue = Alpaca(self, self.ALPACA_API_KEY, self.ALPACA_SECRET_KEY, endpoint=self.ALPACA_BASE_URL)
			logger.info("Venues set up")
			return True
		except Exception as ex:
			logger.info(f"Couldn't set up all venues. Exception: {ex}")
			return False

	def stock_trade(self, symbol, side, quantity):  # Executes a delta neutral trade between IBIT and XBTUSD
		# Todo: Implement this
		return stock_result
		
	@http.route
	def get_trade(self, data):  # Make a synthetic trade
		logger.info(f"Data: {data=}")
		
		result = self.stock_trade(data['symbol'], data['side'], float(data['quantity']))
						
		return "Success"
