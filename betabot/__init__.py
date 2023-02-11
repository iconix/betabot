import logging
import os

try:
    import dotenv
    dotenv.load_dotenv(verbose=True)  # load .env vars
except ImportError:
    pass

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
)
logging.captureWarnings(True)
