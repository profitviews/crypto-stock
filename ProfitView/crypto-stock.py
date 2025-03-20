from profitview import Link, logger, http
import os
import json
import math
import asyncio
import time
from my.venues import BitMEX, Alpaca
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import pandas as pd
import requests
from bs4 import BeautifulSoup
import io
import csv

load_dotenv()

def get_ibit_btc_holdings_and_shares_outstanding():
	headers = {
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
	}
	product_url = "https://www.ishares.com/us/products/333011/ishares-bitcoin-trust"
	response = requests.get(product_url, headers=headers)	
	
	soup = BeautifulSoup(response.text, 'html.parser')
	holdings_link = None

	# Look for the specific link by class or text
	for a in soup.find_all('a', href=True):
		if 'icon-xls-export' in a.get('class', []) or 'detailed holdings and analytics' in a.text.lower():
			holdings_link = a['href']
			break
	
	if not holdings_link.startswith('http'):
		holdings_link = "https://www.ishares.com" + holdings_link
		
	file_response = requests.get(holdings_link, headers=headers)
	
	preamble = file_response.text.splitlines()[:8]
	shares_outstanding = None
	for line in csv.reader(preamble):
		if line and "Shares Outstanding" in line[0]:
			shares_outstanding = line[1].strip('"')
			break
			
	df = pd.read_csv(io.StringIO(file_response.text), skiprows=9)

	# Extract BTC Held from Quantity column
	btc_row = df[df['Ticker'] == 'BTC']
	if not btc_row.empty:
		btc_held = btc_row['Quantity'].values[0]
		print(f"BTC Held: {btc_held}")
		
	return [float(btc_held.replace(",","")), int(float(shares_outstanding.replace(",","")))]

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
	ALPACA_STREAM_URL = 'wss://stream.data.alpaca.markets/v2/iex'
	ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')

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
            self.stock_venue.add_callback(self.on_price_update)
            # Start stream in background after initialization
            self.schedule_stream()
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

    def schedule_stream(self):
        """Schedule the WebSocket stream to start in the background."""
        if not self.venues_ready or not self.stock_venue:
            logger.warning("Venues not ready; cannot schedule stream")
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("Event loop running; scheduling stream task")
                loop.create_task(self.start_stream(symbols=['IBIT']))
            else:
                logger.warning("Event loop not running; scheduling stream in new thread")
                import threading
                threading.Thread(target=lambda: asyncio.run(self.start_stream(symbols=['IBIT'])), daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to schedule stream: {e}")

    def on_start(self):
        """Synchronous start method; logs startup."""
        logger.info("Starting algo")
        if not self.venues_ready:
            logger.warning("Venues not ready yet; stream scheduled in __init__")
        # Stream should already be scheduled by __init__

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

    def on_price_update(self, price_data):
        """Handle WebSocket price updates."""
        logger.info(f"Price update received: {price_data}")
        bid = price_data["bid"]
        ask = price_data["ask"]
        logger.info(f"IBIT Bid: {bid}, Ask: {ask}")
		
	@http.route
    def get_start_stream(self, data):
        """HTTP endpoint to manually start streaming."""
        logger.info("Received request to start stream via HTTP")
        self.schedule_stream()
        return {"status": "Stream start requested"}

    def order_update(self, src, sym, data): pass
    def fill_update(self, src, sym, data): pass
    def position_update(self, src, sym, data): pass
    def quote_update(self, src, sym, data): pass
    def trade_update(self, src, sym, data): pass

	@http.route
	def get_ibit_btc(self, data):
		return get_ibit_btc_holdings()

	@http.route
	def get_ibit_shares(self, data):
		return get_ibit_btc_holdings_and_shares_outstanding()

	@http.route
    def get_prices(self, data):

		ibit_share_price = self.stock_venue.mark_price(data['stock'])  # IBIT share price in USD
		total_shares_outstanding, total_btc_held = get_ibit_btc_holdings_and_shares_outstanding()  # Total Bitcoin held by IBIT

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
