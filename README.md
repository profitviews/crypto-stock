# Crypto Fiat

A simple immplementation of a system that allows users to trade fiat contracts in order to flatten their dollar exposure on crypto transactions so that they can instead be exposed to another fiat currency (presumably their local one).

This is my idea for this project and blog:

- [ ] Create a simple implementation of the system
- [ ] Blog about it
- [ ] ???
- [ ] Profit

## Simple Implementation

### Part 1: Synthetic EUR BTC

Provide a synthetic EUR BTC contract that allows users to trade EUR BTC in a similar way to how they would trade BTC perps normally (against USD).

Then, put that together as a reasonable simple trading algorithm.

Key requirements:
- It should attempt to be transactional.  That is, when making a EUR BTC trade, it should attempt to complete all parts of the trade and if it fails, it should attempt to reverse all parts of the trade that have already been completed.
- It should keep track of the all parts of the trade if possible.

### Part 2: IBIT vs BTC perp arbitrage

A simple strategy to trade the BTC perp when the IBIT price deviates from the BTC perp price based on NAV.

### Part 3: Combine the parts

Combine the parts into a single trading algorithm: an IBIT vs BTC perp arbitrage algorithm that takes into account the trader's EUR exposure.



