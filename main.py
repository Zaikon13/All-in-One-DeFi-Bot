# main.py - All-in-One-DeFi-Bot Entry Point

"""
This file is kept for backward compatibility.
The main worker logic has been moved to worker.py

To run the worker:
    python -u worker.py
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

if __name__ == "__main__":
    logger.info("Please run: python -u worker.py")
    logger.info("The worker logic has been moved to worker.py for better structure.")
