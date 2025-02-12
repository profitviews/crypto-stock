You may have noted my previous blogs have explored some (relatively) esoteric trading strategies: [News signals](https://profitview.net/blog/what-i-learned-when-building-an-ai-news-trading-bot){:target="_blank"}, and getting signals from [DeFi vaults](https://profitview.net/blog/how-i-used-deepseek-to-build-a-profitable-defi-trading-algorithm-in-one-morning){:target="_blank"}.  That was to demonstrate ProfitView's flexibility and extensibility.

ProfitView currently support crypo exchange - but I was thinking that given our algo platform is **full** Python 3, this means that _if you want to_, you can yourself extend to other asset classes prior to us getting around to adding support.

Of course, this won't work for those writing _Bots_ (since it is the end-user who needs the exchange connection).  But we do still fully support our Trading side of the platform, which leaves you in control of execution.

Writing this blog brought me back to a previous [webinar with BitMEX](https://profitview.net/events/getting-started-with-trading-bots){:target="_blank"}.  In preparation for that, I wrote a simple grid trading algorithm.  But there was some boilerplate complexities (which our Signal system now makes unnecessary).  Because, in order to bring in the other asset class platforms I couldn't use the Signal system, I would be helpful to re-use the code from that webinar.

Of course, the way to do this would not be to cut-and-paste - bad form!  I must abstract the common code into a package and import it into _both_ algos.  So, let's do that.

## Abstracting the Common Code

The algo we demonstrated in the BitMEX webinar was a simple grid trading algorithm.  You can find the code in our github repo 
[Grid Bot](https://github.com/profitviews/grid-bot){:target="_blank"} under `src/webinar/2/Starter.py`.  
There code I wanted to reuse abstracts a `Venue` class, in particular so that exchange specifics like tick and lot sizes along 
with API limits and so on are handled in a central place.

The natural way to share this code would be to put it into a package and import it into both algos.  But ProfitView's algo platform consists 
of containers with code written as "special" Python files how would I create  a package that could be imported into both algos?

In fact, if your have an ActiveTrader subscription, you can connect to your container via `ssh`.  So, your can write your package elsewhere and just `scp` it into the container.

In ProfitView, in your Signals tab, click Settings and you'll and under SSH Key, you'll see the `ssh` command you need to connect to your container.

![ssh to container](ssh-to-container.png)

Actually I did it differently.  I use Linux (Ubuntu).  I'm sure this will work on Macs as well and there will be a way to do it on Windows.  You can use [`sshfs`](https://github.com/libfuse/sshfs){:target="_blank"} to mount the container into your local file system.  Then, you can just develop your package locally and just copy it into the container when you need to test.  This works flawlessly.  It even works with the ProfitView feature of updating code while the algo runs: you just copy it over, and the next code path will use the new version.  Adapt this the line below to your container's details.

Deciding on `bots` as the mounted name of the container (and mounting it in the home directory), the command is:

```bash
cd ~
sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,kernel_cache,auto_cache -p 12345 trader@12.34.56.78: bots
```	

I extracted out the `Venue` hierachy into a `venues.py` file and decided on `my` as "my" local package name:

```bash
mkdir -p ~/bots/src/my
cp my/venues.py ~/bots/src/my
```

As I developed `venues.py`, I just repeated `cp my/venues.py ~/bots/src/my` to update the container.  As I mentioned, this can be done while the algo is running.

## Incorporating Non-crypto Venues

My intention in this blog was to show a real-world use-case involving a supported venue (BitMEX) and a non-crypto venue.  Looking around, and thinking of a good project that worked with FX, I found that OANDA has a [REST API](https://developer.oanda.com/rest-live-v20/){:target="_blank"} that would be perfect for this.  I got an account and got it basically working.  Good.

My idea was to create a synthetic currency of the form `[crypto][fiat]`.  I would sell a (non-US dollar) fiat currency on the FX venue for dollars then buy a crypto perp (against dollar).  The effect should be that I've sold the fiat and bought the crypto - that is I had a position in the `[crypto][fiat]` synthetic currency.

Initially I thought I'd go further and write a full trading algorithm for it.  In this effort I came up against a problem: while [OANDA docs](https://developer.oanda.com/rest-live-v20/development-guide/){:target="_blank"} suggest there's a Websocket API, I couldn't get it to work.  I reached out to OANDA support but they seemed unable to help.  On their Github there's a an example project [py-api-streaming](https://github.com/oanda/py-api-streaming){:target="_blank"} - but it simply didn't work and it seems unmaintained.

**If anyone at OANDA wants to help me out, I'd be very happy to add a full trading algorithm.**

Nevertheless, I can demostrate trading these synthetic currencies.  Once the Venue's been constructed the logic is straightforward:

```python
	def crypto_fiat_trade(self, symbol, side, quantity):  # Executes a sythetic market order

		# Get the record for the symbol: FX, Crypto and the crypto's "lot size" (in USD)
		# See the Github for the full code
		synthetic = self.synthetics.get(symbol)  # Returns a structure like {'fx': 'EUR_USD', 'crypto': 'ETHUSD', 'lot': 237.0}
		usd_lot = synthetic['lot']  # The size of the crypto lot in USD
		fiat_rate = self.fx_venue.mark_price(synthetic['fx'])  # Get the USD conversion rate
		usd_quantity = quantity*fiat_rate  # The quantity in USD
		
		# Get the number of lots for this quantity
		usd_lots = math.floor(usd_quantity/usd_lot)  # As much of the quantity as can be traded on the crypto side
		if usd_lots == 0: return "Failure: quantity less than crypto lot size"
		usd_size = usd_lots*usd_lot  # The effective size possible for the FX trade
		
		fx_side = "buy" if side == "sell" else "buy"
		crypto_symbol = synthetic['crypto']
		fx_symbol = synthetic['fx']

		# Do the trade
		fx_result = self.fx_venue.place_order(synthetic['fx'], fx_side, usd_size)
		crypto_result = self.crypto_venue.place_order(synthetic['crypto'], side, usd_lots)
		
		return fx_result, crypto_result
```

The code is in the repo [here](https://github.com/profitviews/crypto-fiat){:target="_blank"}.  The Bot code is in `ProfitView/crypto-fiat.py` and the library code is in `my/venues.py`.  I also have a Jupyter notebook in the repo that I used to develop the library code - see `src/crypto-fiat.ipynb`.

## Conclusion

An actual trading algorithm could be fairly easily written even without a functioning Websocket API.  There is Websocket code that *should* work in `my/venues.py` - if the OANDA guys (or anyone else) can help me out with their end.  I've also implemented a `Venue` for [Alpaca](https://alpaca.markets/){:target="_blank"} - but that will be for another blog.
