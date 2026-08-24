import logging
import sys

# Single shared logger. Per the assessment's "Observability" requirement, every
# completed registration payload and every inbound Vapi webhook gets logged here
# at minimum, to stdout - a real deployment would ship this to a log aggregator.

logger = logging.getLogger("carecloud")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)
