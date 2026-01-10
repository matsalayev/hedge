#!/usr/bin/env python3
"""
Hedging Grid Robot - CLI Entry Point

Standalone rejimda robotni ishga tushirish

Usage:
    python run.py
    python run.py --symbol ETHUSDT --leverage 20
    python run.py --demo --debug
"""

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from hedging_robot.config import RobotConfig
from hedging_robot.robot import HedgingRobot


def setup_logging(debug: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Reduce noise from aiohttp
    logging.getLogger('aiohttp').setLevel(logging.WARNING)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Hedging Grid Robot - Grid Hedging Trading Bot'
    )

    # Basic options
    parser.add_argument('--symbol', type=str, help='Trading pair (e.g., BTCUSDT)')
    parser.add_argument('--leverage', type=int, help='Leverage (1-125)')
    parser.add_argument('--demo', action='store_true', help='Use demo mode')
    parser.add_argument('--real', action='store_true', help='Use real mode')

    # Grid options
    parser.add_argument('--multiplier', type=float, help='Martingale multiplier')
    parser.add_argument('--space-percent', type=float, help='Grid spacing (percent)')
    parser.add_argument('--space-orders', type=int, help='Orders per grid level')

    # Entry options
    parser.add_argument('--timeframe', type=str, help='Timeframe (1m, 5m, 1H, etc.)')
    parser.add_argument('--no-sma-sar', action='store_true', help='Disable SMA/SAR entry')
    parser.add_argument('--cci-period', type=int, help='CCI period (0 to disable)')

    # Profit options
    parser.add_argument('--single-profit', type=float, help='Single order profit target')
    parser.add_argument('--pair-profit', type=float, help='Pair global profit target')

    # Money options
    parser.add_argument('--base-lot', type=float, help='Base lot size')

    # Debug
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    return parser.parse_args()


def apply_args_to_config(config: RobotConfig, args):
    """Apply CLI arguments to config"""
    if args.symbol:
        config.trading.SYMBOL = args.symbol

    if args.leverage:
        config.trading.LEVERAGE = args.leverage

    if args.demo:
        config.api.DEMO_MODE = True
    elif args.real:
        config.api.DEMO_MODE = False

    if args.multiplier is not None:
        config.grid.MULTIPLIER = args.multiplier

    if args.space_percent is not None:
        config.grid.SPACE_PERCENT = args.space_percent

    if args.space_orders is not None:
        config.grid.SPACE_ORDERS = args.space_orders

    if args.timeframe:
        config.entry.TIMEFRAME = args.timeframe

    if args.no_sma_sar:
        config.entry.USE_SMA_SAR = False

    if args.cci_period is not None:
        config.entry.CCI_PERIOD = args.cci_period

    if args.single_profit is not None:
        config.profit.SINGLE_ORDER_PROFIT = args.single_profit

    if args.pair_profit is not None:
        config.profit.PAIR_GLOBAL_PROFIT = args.pair_profit

    if args.base_lot is not None:
        config.money.BASE_LOT = args.base_lot

    if args.debug:
        config.DEBUG = True


async def main():
    """Main entry point"""
    args = parse_args()

    # Setup logging
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 60)
    print("    HEDGING GRID ROBOT")
    print("    Grid Hedging Trading Bot for Bitget Futures")
    print("=" * 60 + "\n")

    # Load config
    config = RobotConfig()

    # Apply CLI args
    apply_args_to_config(config, args)

    # Validate
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Create and run robot
    robot = HedgingRobot(config)

    try:
        await robot.start()
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await robot.stop()

    print("\n\nRobot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
