import logging
import os
from my.venues import Alpaca
from dotenv import load_dotenv
from pathlib import Path
import asyncio

# Configure logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = Path.home() / 'prod-bot' / '.env'
if not env_path.exists():
    logger.error(f"Environment file not found at {env_path}")
    exit(1)
load_dotenv(env_path)

# Validate API credentials
ALPACA_PAPER_API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
ALPACA_PAPER_API_SECRET = os.getenv('ALPACA_PAPER_API_SECRET')

if not ALPACA_PAPER_API_KEY or not ALPACA_PAPER_API_SECRET:
    logger.error("Missing required Alpaca API credentials in .env file")
    exit(1)

ALPACA_DATA_ENDPOINT = 'https://data.alpaca.markets'
ALPACA_STREAM_URL = 'wss://stream.data.alpaca.markets/v2/iex'

# Define callback function outside main()
def handle_price_update(price_data):
    logger.info(f"Received price update: {price_data}")

async def main():
    try:
        logger.info("Initializing Alpaca venue")
        alpaca_venue = Alpaca(
            None, 
            ALPACA_PAPER_API_KEY, 
            ALPACA_PAPER_API_SECRET,
            data_endpoint=ALPACA_DATA_ENDPOINT,
            stream_url=ALPACA_STREAM_URL
        )

        contract = 'IBIT'
        try:
            instruments = alpaca_venue.get_instruments()
            if contract in [i['symbol'] for i in instruments]:
                logger.info(f"{contract} is available")
            else:
                logger.warning(f"{contract} is not available")
                return
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
            return

        # Register the callback with the venue instance
        alpaca_venue.add_callback(handle_price_update)

        logger.info(f"Starting WebSocket stream for {contract}")
        await alpaca_venue.start_stream([contract])

    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    async def cancel_on_x():
        while True:
            try:
                user_input = await asyncio.to_thread(input, "Press 'X' to cancel: ")
                if user_input.strip().lower() == "x":
                    logger.info("Cancellation requested. Stopping...")
                    break
            except (EOFError, KeyboardInterrupt):
                logger.info("Input stream closed. Stopping...")
                break

    async def runner():
        try:
            main_task = asyncio.create_task(main())
            cancel_task = asyncio.create_task(cancel_on_x())
            
            done, pending = await asyncio.wait(
                {main_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            if cancel_task in done:
                main_task.cancel()
                logger.info("Main task has been cancelled.")
                try:
                    await asyncio.wait_for(main_task, timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning("Main task did not cancel cleanly within timeout")
                except Exception as e:
                    logger.error(f"Error during cancellation: {e}")
            
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error during task cleanup: {e}")
                    
        except Exception as e:
            logger.error(f"Unexpected error in runner: {e}", exc_info=True)
            raise

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)