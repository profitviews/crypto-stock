from profitview import Link, logger, http
import os
import asyncio
import threading
import requests
import io
import csv
from my.venues import BitMEX, Alpaca
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup

load_dotenv()

def get_ishares_data(product_url):
	"""
	Scrape iShares site for required product information: BTC held and Shares Outstanding
	"""

	base_url = 'https://www.ishares.com'
	products = '/us/products'
	
	headers = {
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
	}
	response = requests.get(base_url + products + product_url, headers=headers)
	
	soup = BeautifulSoup(response.text, 'html.parser')
	holdings_path = ""

	for a in soup.find_all('a', href=True):
		if 'detailed holdings and analytics' in a.text.lower():
			holdings_path = a['href']
			break
	
	file_response = requests.get(base_url + holdings_path, headers=headers)
	
	# The CSV file is in two sections - the "preamble" and main data
	lines_in_preamble = 8
	
	preamble = file_response.text.splitlines()[:lines_in_preamble]
	shares_outstanding_string = ""
	for line in csv.reader(preamble):
		if line and "Shares Outstanding" in line[0]:
			shares_outstanding_string = line[1].strip('"')
			break
	
	shares_outstanding = int(float(shares_outstanding_string.replace(",","")))
	
	df = pd.read_csv(io.StringIO(file_response.text), skiprows=lines_in_preamble + 1)

	# Extract BTC Held from Quantity column
	btc_row = df[df['Ticker'] == 'BTC']
	btc_held = 0.0
	if not btc_row.empty:
		btc_held_string = btc_row['Quantity'].values[0]
		btc_held = float(btc_held_string.replace(",",""))
		
	return [btc_held, shares_outstanding]

def calculate_implied_btc_price(share_price, total_btc_held, total_shares_outstanding):
    """
    Calculate the implied Bitcoin price from IBIT share price.
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
	ALPACA_STREAM_URL = 'wss://stream.data.alpaca.markets/v2/iex'
	PRODUCT_URL = '/333011/ishares-bitcoin-trust'
	PRODUCT_SYMBOL = 'IBIT'

	def __init__(self):
        self.running = False
        self.stock_venue = None
        self.crypto_venue = None
        self.venues_ready = False
        
        try:
            super().__init__()
            self.venue_setup()
            self.venues_ready = True
            # Register callback after venues are set up
            self.stock_venue.add_callback(self.on_ibit_price_update)
			self.ibit_btc, self.ibit_shares = get_ishares_data(self.PRODUCT_URL)
			self.ibit_quote = {}
            # Start stream in background after initialization
            self.schedule_stream(self.PRODUCT_SYMBOL)
            logger.info("Initialization complete; venues ready")
        except Exception as e:
            logger.error(f"Exception in __init__ during venue setup: {e}")
            self.venues_ready = False

    def venue_setup(self):
        try:
            self.stock_venue = Alpaca(
                self, self.ALPACA_PAPER_API_KEY, self.ALPACA_PAPER_API_SECRET,
                data_endpoint=self.ALPACA_DATA_ENDPOINT, stream_url=self.ALPACA_STREAM_URL)
            self.crypto_venue = BitMEX(self)
            logger.info("Venues set up successfully")
            return True
        except Exception as ex:
            logger.error(f"Couldn't set up venues. Exception: {ex}")
            self.stock_venue = None
            self.crypto_venue = None
            raise

    def schedule_stream(self, symbol):
        """Schedule the WebSocket stream to start in the background."""
        if not self.venues_ready or not self.stock_venue:
            logger.warning("Venues not ready; cannot schedule stream")
            return
        try:
			logger.warning("Scheduling stream in new thread")
			threading.Thread(target=lambda: asyncio.run(self.start_stream(symbols=[symbol])), daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to schedule stream: {e}")

    def on_start(self):
        """Synchronous start method; logs startup."""
        logger.info("Starting algo")
        if not self.venues_ready:
            logger.error("Venues not ready yet; stream scheduled in __init__")

    async def start_stream(self, symbols=["IBIT"]):
        """Asynchronous method to start the WebSocket stream."""
        if self.running:
            logger.info("Stream already running")
            return
        self.running = True
        logger.info(f"Starting stream for symbols: {symbols}")
        try:
            await self.stock_venue.start_stream(symbols)
        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            self.running = False
            logger.info("Stream stopped")

    def on_ibit_price_update(self, price_data):
        """Handle WebSocket price updates."""
        logger.info(f"Price update received: {price_data}")
        self.ibit_quote = { 'bid': price_data["bid"], 'ask': price_data["ask"] }
		
        logger.info(f"IBIT: {self.ibit_quote}")
		
    def quote_update(self, src, sym, data):
		bid = data['bid'][0]
		ibit_bid = self.ibit_quote.get('bid')
		if ibit_bid: 
			implied_ibit_bid = calculate_implied_btc_price(ibit_bid, self.ibit_btc, self.ibit_shares)
			logger.info(f"Bid difference (Premium/Discount): ${(implied_ibit_bid - bid):,.2f} USD/BTC")

		ask = data['ask'][0]
		ibit_ask = self.ibit_quote.get('ask')
		if ibit_ask:
			implied_ibit_ask = calculate_implied_btc_price(ibit_ask, self.ibit_btc, self.ibit_shares)
			logger.info(f"Ask difference (Premium/Discount): ${(implied_ibit_ask - ask):,.2f} USD/BTC")

	@http.route
    def get_start_stream(self, data):
        """HTTP endpoint to manually start streaming."""
        logger.info("Received request to start stream via HTTP")
        self.schedule_stream()
        return {"status": "Stream start requested"}

    def order_update(self, src, sym, data): pass
    def fill_update(self, src, sym, data): pass
    def position_update(self, src, sym, data): pass
    def trade_update(self, src, sym, data): pass

	@http.route
	def get_ibit_btc(self, data):
		return get_ibit_btc_holdings()

	@http.route
	def get_ibit_shares(self, data):
		return get_ishares_data(self.PRODUCT_URL)

	@http.route
    def get_prices(self, data):

		ibit_share_price = self.stock_venue.mark_price(data['stock'])  # IBIT share price in USD
		current_btc_price = self.crypto_venue.mark_price(data['crypto'])  # Approximate BTC price from X post on Feb 25

		# Calculate the implied Bitcoin price
		implied_price = calculate_implied_btc_price(ibit_share_price, self.ibit_btc, self.ibit_shares)

		# Print the result
		logger.info(f"IBIT Share Price: ${ibit_share_price:.2f}")
		logger.info(f"Bitcoin per Share Ratio: {self.ibit_btc / self.ibit_shares:.7f} BTC/share")
		logger.info(f"Implied Bitcoin Price: ${implied_price:,.2f} USD/BTC")

		# Optional: Compare with a known BTC price for sanity check (e.g., Feb 25 estimate)

		logger.info(f"Estimated Market Bitcoin Price: ${current_btc_price:,.2f} USD/BTC")
		logger.info(f"Difference (Premium/Discount): ${(implied_price - current_btc_price):,.2f} USD/BTC")

		return data

    @http.route
    def post_route(self, data):
        """Definition of POST request endpoint - see docs for more info"""
        return data
