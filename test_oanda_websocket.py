import logging
import os
from my.venues import OANDA
from dotenv import load_dotenv
from pathlib import Path
import asyncio


env_path = Path(__file__) / '.env'  # Adjust this path as needed
load_dotenv(env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# OANDA API Credentials
ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID')
API_KEY = os.getenv('OANDA_API_KEY')

async def main():
    logger.info(f"{env_path=}")
    logger.info(f"{ACCOUNT_ID=}")
    logger.info(f"{API_KEY=}")

    # Initialize the OANDA venue
    oanda_venue = OANDA(None, ACCOUNT_ID, API_KEY, endpoint='https://api-fxpractice.oanda.com')
    contract = 'USD_JPY'
    if contract in [i['symbol'] for i in oanda_venue.get_instruments()]:
        logger.info(f"{contract} is available")
    else:
        logger.info(f"{contract} is not available")
        return

    # Define a callback to handle price updates
    @oanda_venue.callback
    def handle_price_update(price_data):
        logger.info(f"Received price update: {price_data}")

    # Start the WebSocket stream
    await oanda_venue.start_stream(f"wss://stream-fxpractice.oanda.com/v3/accounts/{ACCOUNT_ID}/pricing/stream?instruments={contract}")

if __name__ == "__main__":
    async def cancel_on_x():
        while True:
            user_input = await asyncio.to_thread(input, "Press 'X' to cancel: ")
            if user_input.strip().lower() == "x":
                logger.info("Cancellation requested. Stopping...")
                break

    async def runner():
        main_task = asyncio.create_task(main())
        cancel_task = asyncio.create_task(cancel_on_x())
        done, pending = await asyncio.wait(
            {main_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done:
            main_task.cancel()
            logger.info("Main task has been cancelled.")
            await asyncio.gather(main_task, return_exceptions=True)
        for task in pending:
            task.cancel()

    asyncio.run(runner())