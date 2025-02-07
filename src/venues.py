import builtins
import logging
import json
import time
import requests
import asyncio
import websockets
from typing import Callable, List
from functools import wraps
from http.client import HTTPConnection  # Import for debugging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Enable detailed HTTP logging for debugging:
HTTPConnection.debuglevel = 1
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

class Venue:
	def __init__(self, instruments, venue, api_key=None):
		# Get parameters specific to this instrument
		self.instruments = instruments
		self.venue = venue
		self.__current_symbol = None
		self.__current_instrument = None
		self.api_key = api_key
		self.callbacks: List[Callable[[dict], None]] = []

	def _instrument(self, symbol):
		if symbol != self.__current_symbol:
			instrument_data = [i for i in self.instruments if i['symbol'] == symbol]
			self.__current_instrument = instrument_data[0] if instrument_data else None
			self.__current_symbol = symbol if instrument_data else None 

		return self.__current_instrument
	
	def tick(self, symbol):
		if i := self._instrument(symbol):
			return i['tickSize']
		return None
	
	def lot(self, symbol):
		if i := self._instrument(symbol):
			return i['lotSize']
		return None
	
	def standard_size(self, symbol, fiat_amount):
		instrument = self._instrument(symbol)
		if not instrument:
			raise ValueError(f"Symbol {symbol} not found")
        
		mark_price = self.mark_price(symbol)
		lot_size = instrument['lotSize']
		return int(fiat_amount / (mark_price * lot_size))

	def mark_price(self, symbol):
		raise NotImplementedError("Subclasses should implement this method")
	
	# WebSocket Client Base Functionality
	def add_callback(self, callback: Callable[[dict], None]):
		"""Add a callback function that will be called when a new price update is received."""
		self.callbacks.append(callback)
	
	def callback(self, func: Callable[[dict], None]) -> Callable[[dict], None]:
		"""Decorator to register a function as a callback, supporting both functions and instance methods."""
		@wraps(func)
		def wrapper(*args, **kwargs):
			if args and hasattr(args[0], func.__name__):  # Check if it's a method
				method_self = args[0]  # Extract 'self' from instance method
				def bound_callback(price_data):
					func(method_self, price_data)  # Call method with 'self'
				self.add_callback(bound_callback)
			else:
				self.add_callback(func)
			return func
		return wrapper

	async def _stream_prices(self, stream_url):
		"""
		Streams prices from a WebSocket, manually managing the connection.
		"""
		parsed_url = urlparse(stream_url)
		host = parsed_url.netloc
		path = parsed_url.path + "?" + parsed_url.query if parsed_url.query else parsed_url.path

		# Manually construct the headers.  Note:  These MUST be bytes.
		headers = [
			(b"Host", host.encode()),
			(b"Authorization", f"Bearer {self.api_key}".encode()),
			(b"Connection", b"Upgrade"),
			(b"Upgrade", b"websocket"),
			(b"Sec-WebSocket-Key", b"dGhlIHNhbXBsZSBub25jZQ=="),  # Base64 encoded, but value doesn't matter
			(b"Sec-WebSocket-Version", b"13"),
		]

		# Get the event loop
		loop = asyncio.get_running_loop()

		try:
			# Create the connection.  This does NOT automatically handle the handshake.
			transport, protocol = await loop.create_connection(
				lambda: websockets.client.WebSocketClientProtocol(extra_headers=headers),
				host=parsed_url.hostname,
				port=parsed_url.port,
				ssl=True,  # OANDA requires SSL
			)

			# Manually perform the handshake.
			try:
				await protocol.handshake(
					host=host,
					path=path,
					subprotocols=None,
					extra_headers=headers,
				)
				print("WebSocket connection opened.")

				# Now we can receive messages.
				while True:
					try:
						message = await protocol.recv()
						data = json.loads(message)
						if "bids" in data and "asks" in data:
							bid = data["bids"][0]["price"]
							ask = data["asks"][0]["price"]
							price_update = {"bid": bid, "ask": ask}
							for callback in self.callbacks:
								callback(price_update)
					except websockets.exceptions.ConnectionClosed as e:
						print(f"WebSocket connection closed: {e}")
						break  # Exit the loop on connection close
					except Exception as e:
						print(f"An unexpected error occurred: {e}")
						break # Exit loop on other errors.

			except websockets.exceptions.InvalidHandshake as e:
				print(f"WebSocket handshake failed: {e}")
			except Exception as e:
				print(f"An unexpected error occurred during handshake: {e}")
			finally:
				await protocol.close()
				print("WebSocket connection closed.")

		except OSError as e:
			print(f"Failed to connect: {e}")
		except Exception as e:
			print(f"An unexpected error occurred during connection: {e}")

	async def start_stream(self, stream_url):
		"""Start the WebSocket streaming in an asyncio event loop."""
		await self._stream_prices(stream_url)
		

class BitMEX(Venue):
	NAME = 'BitMEX'
	INSTRUMENT_ENDPOINT = 'instrument'
	INSTRUMENT_PAGE_SIZE = 500
	ALGO_PARAMETERS = { 'tickSize': 'float'
					  , 'lotSize': 'int'
					  , 'markPrice': 'float'
					  , 'isInverse': 'bool'
					  , 'multiplier': 'float'
					  , 'settlCurrency': 'str'
					  , 'symbol': 'str'
					  }
	RATE_LIMIT_DELAY = 0.5

	def __type_parameters(self, instruments):
		typed_instruments = []
		for i in instruments:
			ti = {}
			for p, v in BitMEX.ALGO_PARAMETERS.items():
				ti[p] = getattr(builtins, v)(i[p]) if i[p] else i[p]
			typed_instruments.append(ti)
		return typed_instruments

	def __init__(self, trading, rate_limit_delay=RATE_LIMIT_DELAY):
		instrument_count = 0
		all_instruments_data = []
		instrument_meta_data = {}
		self.trading = trading
		self.rate_limit_delay = rate_limit_delay

		while True:  # Max of 500 results per call, so paginate
			         # See: https://www.bitmex.com/api/explorer/#!/Instrument/Instrument_get
			instruments = trading.call_endpoint(
				self.NAME,
				self.INSTRUMENT_ENDPOINT,
				'public',
				method='GET', params={
					'count': 500, 
					'start': instrument_count,
					'columns': json.dumps([*self.ALGO_PARAMETERS])
				})
			instruments_data = [i for i in instruments['data'] if i.get('settlCurrency') and i.get('markPrice')]
			all_instruments_data += instruments_data
			current_count = len(instruments['data'])
			instrument_count += current_count
			logger.info(f"{instrument_count=}")
			if current_count < self.INSTRUMENT_PAGE_SIZE: break
			time.sleep(self.rate_limit_delay)  # To avoid rate limits
		
		super().__init__(self.__type_parameters(all_instruments_data), self.NAME)

	def mark_price(self, symbol):
		d = self._instrument(symbol)
		if d['isInverse']: mark_price = 1/d['markPrice']
		else: mark_price = d['markPrice']
		return mark_price
		
	def standard_size(self, symbol, fiat_amount):
		mark_price = self.mark_price(symbol)

		d = self._instrument(symbol)

		mark_multiplier = abs(float(d['multiplier']))*mark_price
		
		xbtparams = self.trading.call_endpoint(
			self.NAME,
			self.INSTRUMENT_ENDPOINT,
			'public',
			method='GET', params={
				'symbol': 'XBT', 'columns': 'markPrice'
		})
		xbtMark = float(xbtparams['data'][0]['markPrice'])

		USDt_in_USD = 1e-6  # USDt in $: https://blog.bitmex.com/api_announcement/api-usage-for-usdt-contracts/
					        # and: https://www.bitmex.com/app/restAPI 
		BTC_in_SATOSHI = 1e8
		mark = xbtMark/BTC_in_SATOSHI if d['settlCurrency'] == 'XBt' else USDt_in_USD
		lot = self.lot(symbol)
		minimum_fiat_size = int(lot)*mark*mark_multiplier
		assert(fiat_amount > minimum_fiat_size)
		fiat_multiple = fiat_amount//minimum_fiat_size
		return fiat_multiple*lot

	def place_order(self, symbol, side, quantity, order_type='market', price=None):
		side = side.capitalize()
		if order_type == 'market':
			# Use ProfitView's create_market_order method
			order = self.trading.create_market_order(
				venue=self.NAME,
				sym=symbol,
				side=side,
				size=quantity
			)
		elif order_type == 'limit' and price is not None:
			# Use ProfitView's create_limit_order method
			order = self.trading.create_limit_order(
				venue=self.NAME,
				symbol=symbol,
				side=side,
				quantity=quantity,
				price=price
			)
		else:
			raise ValueError("Invalid order type or missing price for limit order")
		
		return order


class OANDA(Venue):
	NAME = 'OANDA'
	INSTRUMENTS_ENDPOINT = 'v3/accounts/{account_id}/instruments'
	PRICING_ENDPOINT = 'v3/accounts/{account_id}/pricing'
	TRADING_ENDPOINT = 'v3/accounts/{account_id}/orders'
	HEADERS = { 'Content-Type': 'application/json' }

	def __init__(self, trading, account_id, api_key, endpoint='https://api-fxtrade.oanda.com'):
		logger.info(f"{endpoint=}")
		self.trading = trading
		self.account_id = account_id
		self.api_key = api_key
		self.HEADERS['Authorization'] = f'Bearer {self.api_key}'
		self.HEADERS['Content-Type'] = 'application/json'
		self.instruments_endpoint = f'{endpoint}/{self.INSTRUMENTS_ENDPOINT}'.format(account_id=account_id)
		self.pricing_endpoint = f'{endpoint}/{self.PRICING_ENDPOINT}'.format(account_id=account_id)
		self.trading_endpoint = f'{endpoint}/{self.TRADING_ENDPOINT}'.format(account_id=account_id)
		# logger.info(f"{self.instruments_endpoint=}")
		# logger.info(f"{self.pricing_endpoint=}")
		instruments_data = self.get_instruments()
		super().__init__(instruments_data, self.NAME, api_key)

	def get_instruments(self):
		response = requests.get(self.instruments_endpoint.format(account_id=self.account_id), headers=self.HEADERS)
		response.raise_for_status()
		data = response.json()
		# logger.info(f"{data=}")
		instruments = [
			{
				'symbol': i['name'],
				'pipLocation': float(i['pipLocation']),
				'tickSize': 10**float(i['pipLocation']),
				'lotSize': 1,  # OANDA does not use lot size in the traditional sense
				'isInverse': i.get('isInverted', False),
				'multiplier': 1,
				'settlCurrency': i.get('quoteCurrency', 'USD'),
				'markPrice': float(i.get('closeoutAsk', 1))
			}
			for i in data['instruments']
		]
		return instruments

	def mark_price(self, symbol):
		response = requests.get(
			self.pricing_endpoint.format(account_id=self.account_id),
			headers=self.HEADERS,
			params={'instruments': symbol}
		)
		response.raise_for_status()
		pricing_data = response.json()
		return float(pricing_data['prices'][0]['closeoutAsk'])

	def place_order(self, symbol, side, quantity, order_type='MARKET'):
		side = side.lower()
		logger.info(f"OANDA: {side=}")	
		quantity = quantity if side == 'buy' else -quantity
		logger.info(f"OANDA: {quantity=}")	
		order_data = {
			"order": {
				"instrument": symbol,
				"units": quantity,
				"type": order_type,
				"positionFill": "DEFAULT"
			}
		}
		logger.info(f"OANDA: {order_data=}")
		response = requests.post(self.trading_endpoint, json=order_data, headers=self.HEADERS)
		response.raise_for_status()
		return response.json()

	def handle_price_update(self, price_data):
		# Handle real-time price updates
		print(f"Received price update: {price_data}")


class Alpaca(Venue):
	NAME = 'Alpaca'
	INSTRUMENTS_ENDPOINT = 'v2/assets'
	PRICING_ENDPOINT = 'v2/stocks/{symbol}/quotes/latest'
	HEADERS = {'Content-Type': 'application/json'}
	
	def __init__(self, trading, api_key, secret_key, trading_endpoint='https://paper-api.alpaca.markets', data_endpoint='https://data.alpaca.markets'):
		self.trading = trading
		self.api_key = api_key
		self.secret_key = secret_key
		self.HEADERS['APCA-API-KEY-ID'] = self.api_key
		self.HEADERS['APCA-API-SECRET-KEY'] = self.secret_key
		
		# Use trading endpoint for assets
		self.instruments_endpoint = f'{trading_endpoint}/{self.INSTRUMENTS_ENDPOINT}'
		
		# Use data endpoint for quotes
		self.pricing_endpoint = f'{data_endpoint}/{self.PRICING_ENDPOINT}'
		
		instruments_data = self.get_instruments()
		super().__init__(instruments_data, self.NAME)
	
	def get_instruments(self):
		response = requests.get(self.instruments_endpoint, headers=self.HEADERS)
		response.raise_for_status()
		data = response.json()
		instruments = [
			{
				'symbol': i['symbol'],
				'tickSize': 0.01,  # Alpaca typically supports decimal precision
				'lotSize': 1  # Alpaca uses whole shares
			}
			for i in data if i['tradable']
		]
		return instruments

	def mark_price(self, symbol):
		try:
			url = self.pricing_endpoint.format(symbol=symbol)
			print(f"Fetching quote from: {url}")
			response = requests.get(url, headers=self.HEADERS)
			response.raise_for_status()
			pricing_data = response.json()
			if 'quote' in pricing_data and 'ap' in pricing_data['quote']:
				return float(pricing_data['quote']['ap'])
			else:
				print(f"Unexpected response format for symbol {symbol}: {pricing_data}")
				return None
		except requests.exceptions.HTTPError as e:
			print(f"HTTP error occurred: {e}")
			print(f"Response content: {response.content}")
			return None
		except Exception as e:
			print(f"An error occurred: {e}")
			return None

	def place_order(self, symbol, side, quantity, order_type='market'):
		url = f'{self.trading_endpoint}/v2/orders'
		order_data = {
			"symbol": symbol,
			"qty": quantity,
			"side": side,
			"type": order_type,
			"time_in_force": "gtc"
		}
		response = requests.post(url, json=order_data, headers=self.HEADERS)
		response.raise_for_status()
		return response.json()
