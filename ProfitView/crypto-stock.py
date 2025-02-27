from profitview import Link, logger, http
import os
import json
import math
from my.venues import BitMEX, Alpaca
from dotenv import load_dotenv

load_dotenv()


def calculate_implied_btc_price(share_price, total_btc_held, total_shares_outstanding):
    """
    Calculate the implied Bitcoin price from IBIT share price.
    
    Args:
        share_price (float): Current IBIT share price in USD
        total_btc_held (float): Total Bitcoin held by the IBIT trust
        total_shares_outstanding (float): Total number of IBIT shares outstanding
    
    Returns:
        float: Implied Bitcoin price in USD
    """
    # Calculate the Bitcoin per Share Ratio
    btc_per_share_ratio = total_btc_held / total_shares_outstanding
    
    # Calculate the implied Bitcoin price
    implied_btc_price = share_price / btc_per_share_ratio
    
    return implied_btc_price


class Trading(Link):
	ALPACA_API_KEY=os.getenv('ALPACA_API_KEY')
	ALPACA_API_SECRET=os.getenv('ALPACA_API_SECRET')
	ALPACA_PAPER_API_KEY=os.getenv('ALPACA_PAPER_API_KEY')
	ALPACA_PAPER_API_SECRET=os.getenv('ALPACA_PAPER_API_SECRET')
	ALPACA_DATA_ENDPOINT = 'https://data.alpaca.markets'

	def on_start(self):
		if not self.venue_setup():
			logger.error(f"Error getting instrument data from venues - ending algo")
			raise RuntimeError()
			
	def venue_setup(self):
		try:
			self.stock_venue = Alpaca(
				self, 
				self.ALPACA_PAPER_API_KEY, 
				self.ALPACA_PAPER_API_SECRET, 
				data_endpoint=self.ALPACA_DATA_ENDPOINT)
			self.crypto_venue = BitMEX(self)
			logger.info("Venues set up")
			return True
		except Exception as ex:
			logger.info(f"Couldn't set up all venues. Exception: {ex}")
			return False

    def order_update(self, src, sym, data):
        """Called on order updates from connected exchanges"""

    def fill_update(self, src, sym, data):
        """Called on trade fill updates from connected exchanges"""

    def position_update(self, src, sym, data):
        """Called on position updates from connected exchanges"""

    def quote_update(self, src, sym, data):
        """Called on top of book quotes from subscribed symbols"""

    def trade_update(self, src, sym, data):
        """Called on market trades from subscribed symbols"""

    @http.route
    def get_prices(self, data):

		# Example values based on February 26, 2025 estimate
		ibit_share_price = self.stock_venue.mark_price(data['stock'])  # IBIT share price in USD
		total_btc_held = 587698  # Total Bitcoin held by IBIT (as of Feb 20, 2025)
		total_shares_outstanding = 1034000000  # Total shares outstanding (1.034 billion, Feb 20, 2025)

		# Calculate the implied Bitcoin price
		implied_price = calculate_implied_btc_price(ibit_share_price, total_btc_held, total_shares_outstanding)

		# Print the result
		logger.info(f"IBIT Share Price: ${ibit_share_price:.2f}")
		logger.info(f"Bitcoin per Share Ratio: {total_btc_held / total_shares_outstanding:.7f} BTC/share")
		logger.info(f"Implied Bitcoin Price: ${implied_price:,.2f} USD/BTC")

		# Optional: Compare with a known BTC price for sanity check (e.g., Feb 25 estimate)

		current_btc_price = self.crypto_venue.mark_price(data['crypto'])  # Approximate BTC price from X post on Feb 25
		logger.info(f"Estimated Market Bitcoin Price: ${current_btc_price:,.2f} USD/BTC")
		logger.info(f"Difference (Premium/Discount): ${(implied_price - current_btc_price):,.2f} USD/BTC")

		return data

    @http.route
    def post_route(self, data):
        """Definition of POST request endpoint - see docs for more info"""
        return data
