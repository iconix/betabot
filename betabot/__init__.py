import logging
import os

from dotenv import load_dotenv

load_dotenv(verbose=True)  # load .env vars

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
)
logging.captureWarnings(True)
