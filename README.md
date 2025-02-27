See [our blogs](https://profitview.net/blog) for more articles like this.

This blog will _effectively_ be an expansion on my previous one: [Multi-Asset Algorithmic Trading with Python: Extending ProfitView Beyond Crypto to OANDA Forex](https://profitview.net/blog/multi-asset-algorithmic-trading-with-python-extending-profitview-beyond-crypto-to-oanda-forex).  This time we'll be looking at the stock market, and more specifically the Bitcoin ETF of BlackRock.

This will give an opportunity to show how to use ProfitView but also, since we'll trade with Alpaca, the usage of its websocket streaming prices to construct a reasonable algo.

# Overall Scheme

The premise of the algo is simple:

1. We'll trade a delta neutral position between IBIT and XBTUSD
2. We'll use ProfitView to stream the price of XBTUSD from BitMEX via the `trade_update()` method of the `Trading` class.
3. We'll use the websocket to stream the price of the other instrument, which is the Bitcoin ETF of BlackRock, IBIT from Alpaca.

We'll calculate the implied NAV of IBIT from the price of XBTUSD and the price of IBIT.  We'll then calculate the delta between this implied NAV and the actual NAV, and trade the difference.

# Implementation

## BitMEX

We'll use the `trade_update()` method of the `Trading` class to stream the price of XBTUSD from BitMEX.

## Alpaca

Alpaca has a websocket streaming API that we can use to stream the price of IBIT.

## NAV Calculation


