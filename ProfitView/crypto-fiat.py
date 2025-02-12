from profitview import Link, logger, http
import os
import json
import math

# See venues.py in the repo. 
# I've chosen to put the code in the `my` directory under `src` in the container
from my.venues import BitMEX, OANDA
from dotenv import load_dotenv


load_dotenv()


class Trading(Link):
	OANDA_API_PRACTICE_URL = os.getenv("OANDA_API_PRACTICE_URL")
	OANDA_API_LIVE_URL = os.getenv("OANDA_API_LIVE_URL")
	OANDA_API_KEY = os.getenv("OANDA_DEMO_API_KEY")
	OANDA_ACCOUNT_ID = os.getenv("OANDA_DEMO_ACCOUNT_ID")
	OANDA_ENV = "practice"
			
	synthetic_mapping = {
		"EUR": "EUR_USD",	
		"JPY": "USD_JPY",
		"AUD": "AUD_USD",
		"GBP": "GBP_USD",
	}
	
	cryptos = ["XBT", "ETH", "AAVE", "ADA", "DOGE", "DOT", "LINK", "LTC", "XRP"]
	
    def on_start(self):
		if not self.venue_setup():
			logger.error(f"Error getting instrument data from venues - ending algo")
			raise RuntimeError()
	
		self.synthetics = {  # Construct a structure of synthetic currencies of the form [fiat][crypto]
			                 # and the mapping to their actual ccys, and add the USD lot size implied by
                             # the crypto lot size
			f"{crypto}{currency}": {
				"fx": self.synthetic_mapping[currency], 
				"crypto": f"{crypto}USD",
				"lot": self.crypto_venue.get_contract_usd_price(f"{crypto}USD")
			}
			for crypto in self.cryptos
			for currency in self.synthetic_mapping.keys()
		}


	def venue_setup(self):
		try:
			self.fx_venue = OANDA(self, self.OANDA_ACCOUNT_ID, self.OANDA_API_KEY, endpoint=self.OANDA_API_PRACTICE_URL)
			self.crypto_venue = BitMEX(self)
			logger.info("Venues set up")
			return True
		except Exception as ex:
			logger.info(f"Couldn't set up all venues. Exception: {ex}")
			return False

	def crypto_fiat_trade(self, symbol, side, quantity):  # Executes a sythetic market order
		# Get the record for the symbol: FX, Crypto and the "lot size" (in USD)
		synthetic = self.synthetics.get(symbol)
		usd_lot = synthetic['lot']
		logger.info(f"{usd_lot=}")

		logger.info(f"{quantity=}")

		fiat_rate = self.fx_venue.mark_price(synthetic['fx'])  # Get the conversion rate
		logger.info(f"{fiat_rate=}")
		usd_quantity = quantity*fiat_rate
		logger.info(f"{usd_quantity=}")
		
		# Get the number of lots for this quantity
		usd_lots = math.floor(usd_quantity/usd_lot)  # As much of the quantity as can be traded on the crypto side
		if usd_lots == 0: return "Failure: quantity less than crypto lot size"
		usd_size = usd_lots*usd_lot  # The effective size possible for the FX trade
		logger.info(f"{usd_size=}")
		
		fx_side = "buy" if side == "sell" else "buy"
		crypto_symbol = synthetic['crypto']
		fx_symbol = synthetic['fx']

		# Do the trade
		fx_result = self.fx_venue.place_order(synthetic['fx'], fx_side, usd_size)
		logger.info(f"{fx_result=}")
		crypto_result = self.crypto_venue.place_order(synthetic['crypto'], side, usd_lots)
		logger.info(f"{crypto_result=}")
		
		return fx_result, crypto_result
		
	@http.route
	def get_trade(self, data):  # Make a synthetic trade
		logger.info(f"Data: {data=}")
		
		result = self.crypto_fiat_trade(data['symbol'], data['side'], float(data['quantity']))
				
		return "Success"
