#!/usr/bin/env python3
"""
Hedging Grid Robot - Server Entry Point

HEMA platformasi bilan integratsiya uchun REST API server

Usage:
    python run_server.py
    python run_server.py --port 8082
    python run_server.py --host 0.0.0.0 --port 8082 --debug
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn


def setup_logging(debug: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set uvicorn loggers
    logging.getLogger('uvicorn').setLevel(level)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING if not debug else logging.INFO)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Hedging Grid Robot - HEMA Integration Server'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=os.getenv('SERVER_HOST', '0.0.0.0'),
        help='Server host (default: 0.0.0.0)'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=int(os.getenv('SERVER_PORT', '8082')),
        help='Server port (default: 8082)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        default=os.getenv('DEBUG', 'false').lower() == 'true',
        help='Enable debug mode'
    )

    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload (development)'
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    # Setup logging
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 60)
    print("    HEDGING GRID ROBOT - SERVER MODE")
    print("    HEMA Platform Integration")
    print("=" * 60)
    print(f"\n    Host: {args.host}")
    print(f"    Port: {args.port}")
    print(f"    Debug: {args.debug}")
    print("\n" + "=" * 60 + "\n")

    # Log configuration
    bot_id = os.getenv('BOT_ID', 'hedging-grid-bot')
    bot_name = os.getenv('BOT_NAME', 'Hedging Grid Robot')
    logger.info(f"Starting {bot_name} (ID: {bot_id})")
    logger.info(f"Listening on http://{args.host}:{args.port}")

    # Run server
    uvicorn.run(
        "hedging_robot.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="debug" if args.debug else "info",
        access_log=args.debug
    )


if __name__ == "__main__":
    main()
