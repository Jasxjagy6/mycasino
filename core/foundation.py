"""Shared casino runtime: imports, configuration, module-level state.

This module is the single source of truth for everything that the
split casino plugins need to run.  Every other module under
``core/`` and ``plugins/`` does ``from core.foundation import *``
to share this namespace.

It is auto-generated from bot.py by .refactor/split_bot.py — do
NOT edit the imports or module-level state here unless you also
rerun the splitter.
"""

import uvloop

uvloop.install()

print("uvloop enabled for high performance async operations")

import logging

import random

import string

import asyncio

import json

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

BASE_DIR = '/root/7'

import warnings

from datetime import datetime, timedelta, timezone

import httpx

import aiohttp

import aiohttp.web

from web3 import Web3, AsyncWeb3

from web3.providers import AsyncHTTPProvider

from eth_account import Account

import secrets # For secure token generation

import hashlib # For hashing PINs

import hmac # For secure key derivation

import traceback # For detailed error logging

import uuid # For generating unique rain IDs

import bisect # For O(log n) leaderboard insertion

import concurrent.futures # For thread pool executors

import sys

warnings.filterwarnings('ignore', category=DeprecationWarning)

warnings.filterwarnings('ignore', message='.*CallbackQueryHandler.*')

from openai import OpenAI

import g4f

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, Bot, ReplyKeyboardMarkup,
    InputMediaPhoto
)

from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler, ChatJoinRequestHandler,
    AIORateLimiter
)

from telegram.constants import ParseMode

from telegram.error import BadRequest, Forbidden

import atexit

from bip_utils import (
    Bip44, Bip44Coins, Bip44Changes, CoinsConf, WifDecoder,
    Bip39SeedGenerator, Bip39MnemonicGenerator, Bip39WordsNum
)

import sqlite3

import aiosqlite

try:
    import asyncpg
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    asyncpg = None

if POSTGRES_AVAILABLE:
    try:
        import postgres_db as pg_db
        USE_POSTGRES_FOR_ALL = True
        logging.info("PostgreSQL database layer loaded successfully")
    except Exception as e:
        logging.warning(f"Failed to load postgres_db module: {e}")
        pg_db = None
        USE_POSTGRES_FOR_ALL = False
else:
    pg_db = None
    USE_POSTGRES_FOR_ALL = False

import qrcode

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    from solders.keypair import Keypair as SoldersKeypair
    from solders.pubkey import Pubkey as SoldersPubkey
    from solders.system_program import TransferParams as SoldersTransferParams, transfer as solders_transfer
    from solders.transaction import Transaction as SoldersTransaction
    from solana.rpc.async_api import AsyncClient as SolanaClient
    import base58
    SOLANA_AVAILABLE = True
except ImportError as e:
    SOLANA_AVAILABLE = False
    print(f"WARNING: Solana libraries not available: {e}")

try:
    from tronpy import Tron
    from tronpy.keys import PrivateKey as TronPrivateKey
    TRON_AVAILABLE = True
except ImportError:
    TRON_AVAILABLE = False
    print("WARNING: Tron library not available. Install with: pip install tronpy")

try:
    from pytoniq_core import Address as TonAddress
    from pytoniq_core.crypto.keys import mnemonic_to_private_key, private_key_to_public_key
    TON_AVAILABLE = True
except ImportError:
    TON_AVAILABLE = False
    print("WARNING: TON library not available. Install with: pip install pytoniq-core")

def _get_env_or_default(env_name: str, default: str, is_secret: bool = False) -> str:
    """Get value from environment variable, fallback to default.
    SECURITY: Set env vars to override hardcoded defaults."""
    import os
    val = os.environ.get(env_name)
    if val:
        if is_secret:
            logging.info(f"Secret {env_name} loaded from environment")
        return val
    return default

BOT_TOKEN = _get_env_or_default('BOT_TOKEN', "8235772615:AAEJ8YG2psk76w8VCT7agyBl7KsxFXS5Dg8", is_secret=True)

HELPER_BOT_TOKEN = _get_env_or_default('HELPER_BOT_TOKEN', "8524914117:AAE1zTiTBm2npMdVguapC0HYbjFdaM56yyY", is_secret=True)

HELPER_BOT_2_TOKEN = _get_env_or_default('HELPER_BOT_2_TOKEN', "8530002434:AAFCzvU4wS9dvyDBKZf1vHPBhhGoyzwIFf4", is_secret=True)

HELPER_BOT_3_TOKEN = _get_env_or_default('HELPER_BOT_3_TOKEN', "8662974400:AAFdnhGVz11nMEoaFYiiHtUSDcnousG-2L0", is_secret=True)

HELPER_BOT_4_TOKEN = _get_env_or_default('HELPER_BOT_4_TOKEN', "8661098728:AAF0Yn9n7DkFka-olCwRxaJiL3I8UZQcDOE", is_secret=True)

HELPER_BOT_5_TOKEN = _get_env_or_default('HELPER_BOT_5_TOKEN', "8679354746:AAESYaIOuivG3c_lTLDuJswzyW9HUdn2mhE", is_secret=True)

HELPER_BOT_6_TOKEN = _get_env_or_default('HELPER_BOT_6_TOKEN', "8621492937:AAGAEWv2wakYbR10gGKPcJGQPXOlwyw5b54", is_secret=True)

_owner_ids_env = os.environ.get('BOT_OWNER_IDS')

if _owner_ids_env:
    BOT_OWNER_IDS = [int(x.strip()) for x in _owner_ids_env.split(',')]
else:
    BOT_OWNER_IDS = [6083286836]  # List of admin Telegram IDs. First ID receives withdrawal notifications.

BOT_OWNER_ID = BOT_OWNER_IDS[0]  # Primary admin (backward compat for withdrawal notifications)

def is_admin(user_id: int) -> bool:
    """Check if a user is a bot admin/owner."""
    return user_id in BOT_OWNER_IDS

MIN_BALANCE = 0.1

DEBUG_EMOJI_GAMES = False  # Set to True to enable detailed emoji game logging

ROLL_SEPARATOR = ", "  # Separator for displaying multiple roll values (e.g., "4, 5, 6")

HILOW_SKIP_NONCE_OFFSET = 1000

HELPER_BOT_ANIMATION_DELAY = 0.3  # Seconds to wait after helper bot sends animation (dice, slots, darts, etc.)

BOT_USERNAME_TAG = "@playcsino"  # Fill in the tag/text users should add to their Telegram name (case-insensitive, e.g. "CasinoBot")

BOT_USERNAME_TAG_NORMALIZED = BOT_USERNAME_TAG.lower().replace("@", "") if BOT_USERNAME_TAG else ""

HOUSE_EDGES = {
    "pvp": 0.005,        # 0.5% - PvP Games (/p, Emoji Duels)
    "originals": 0.01,   # 1.0% - Originals (Dice, Plinko, etc.)
    "slots": 0.04,       # 4.0% - Slots (/sl)
    "sidebets": 0.07,    # 7.0% - Side Bets on emoji games
    "7up": 0.07,         # 7.0% - 7Up7Down game
}

GAME_TYPE_TO_EDGE_CATEGORY = {
    # PvP games
    "pvp_dice": "pvp", "pvp_darts": "pvp", "pvp_goal": "pvp", "pvp_bowl": "pvp",
    "xdxw_dice": "pvp", "xdxw_darts": "pvp", "xdxw_goal": "pvp", "xdxw_bowl": "pvp",
    "group_challenge_dice": "pvp", "group_challenge_darts": "pvp",
    "group_challenge_goal": "pvp", "group_challenge_bowl": "pvp",
    "single_emoji_darts": "pvp", "single_emoji_soccer": "pvp",
    "single_emoji_basket": "pvp", "single_emoji_bowling": "pvp",
    "single_emoji_slot": "pvp",
    # Slots
    "slots": "slots",
    # Originals (default category for everything else)
    "dice_roll": "originals", "predict": "originals", "limbo": "originals",
    "blackjack": "originals", "coin_flip": "originals", "roulette": "originals",
    "mines": "originals", "tower": "originals", "keno": "originals",
    "highlow": "originals", "coinchain": "originals", "coin_chain": "originals",
    "scratch": "originals", "crash": "originals", "plinko": "originals",
    "wheel": "originals",
    "chicken_road": "originals",
    "pvb_dice": "originals", "pvb_darts": "originals", "pvb_goal": "originals",
    "pvb_bowl": "originals",
    # Side bets
    "sidebet_win": "sidebets", "sidebet_lose": "sidebets",
    # 7Up7Down
    "7up7down": "7up", "7up7down_2dice": "7up", "7up7down_3dice": "7up",
    # Dice Rush games
    "classic_rush": "originals", "odd_even_rush": "originals",
    "high_low_rush": "originals", "rainbow_rush": "originals", "blaze_rush": "originals",
}

VIP_BASE_REWARDS = {
    "Bronze": 0.10, "Silver": 0.25, "Gold": 0.50, "Platinum": 1.00,
    "Diamond": 2.00, "Emerald": 3.50, "Ruby": 5.00, "Sapphire": 7.50
}

LINK_PORTAL = ""  # Portal link (leave empty if not available)

LINK_CHANNEL = "https://t.me/escrews"  # Channel link (e.g., "https://t.me/yourchannel")

LINK_CHAT = "https://t.me/playcsino"  # Chat link (e.g., "https://t.me/yourchat")

LINK_SUPPORT = "https://t.me/jashanxjagy"  # Support link (e.g., "https://t.me/yoursupport")

ROULETTE_IMAGE = "roulette_table.jpg"  # Change this to your image filename

WIN_BROADCAST_CHANNEL_ID = "@playcasinowins"  # Example: "-1003848853417" or "@mychannel" or leave empty to disable

SURPRISE_DROP_GROUP = "@playcsino"

PERPLEXITY_API_KEY = _get_env_or_default('PERPLEXITY_API_KEY', "[REDACTED]", is_secret=True)

MEXC_API_KEY = _get_env_or_default('MEXC_API_KEY', "mx0vgltPHKyw92y4qZ", is_secret=True)

MEXC_API_SECRET = _get_env_or_default('MEXC_API_SECRET', "5f4f81217f514a799e4d77842bcc4a26", is_secret=True)

ESCROW_DEPOSIT_ADDRESS = _get_env_or_default('ESCROW_DEPOSIT_ADDRESS', "0xdda0e87f6c1344e07cfce9cefb12f3a286a0fb38")

ESCROW_WALLET_PRIVATE_KEY = _get_env_or_default('ESCROW_WALLET_PRIVATE_KEY', "0bbaf8d35b64859555b1a6acc7909ac349bced46b2fcf2c8d616343fec138353", is_secret=True)

ESCROW_DEPOSIT_NETWORK = "bsc"

ESCROW_DEPOSIT_TOKEN_CONTRACT = "0x55d398326f99059fF775485246999027B3197955" # USDT BEP20

ESCROW_DEPOSIT_TOKEN_DECIMALS = 18

REFERRAL_BET_COMMISSION_RATE = 0.001      # 0.1%

DEPOSIT_ENABLED = True

DEPOSITS_DB = "deposits.db"

POSTGRES_URL = os.environ.get('POSTGRES_URL')  # e.g., "postgresql://user:pass@localhost/casino"

USE_POSTGRES = POSTGRES_AVAILABLE and POSTGRES_URL  # Auto-enable if env var set

if USE_POSTGRES_FOR_ALL and USE_POSTGRES:
    logging.info("FULL POSTGRESQL MODE ENABLED - All user data will be stored in PostgreSQL")

OXAPAY_MERCHANT_KEY = _get_env_or_default('OXAPAY_MERCHANT_KEY', "ONJRRF-JIWZG3-PIUVLS-E9ZRDT", is_secret=True)

OXAPAY_WEBHOOK_HOST = "https://play-casino.app"   # e.g. "https://your-server.com"

OXAPAY_WEBHOOK_PORT = 8090  # Port for the aiohttp webhook listener (changed from 8080 to avoid conflict)

OXAPAY_SUPPORTED_CURRENCIES = {"BTC", "ETH", "USDT", "LTC", "TRX", "BNB", "SOL"}

_oxapay_bot_ref = None            # Will hold the Telegram Bot instance (set at startup)

_oxapay_processed_orders = set()  # In-memory duplicate-payment guard

_oxapay_processed_orders_file = os.path.join(BASE_DIR, 'oxapay_processed_orders.json')

def _load_oxapay_processed_orders():
    """Load processed OxaPay order IDs from disk."""
    global _oxapay_processed_orders
    try:
        if os.path.exists(_oxapay_processed_orders_file):
            with open(_oxapay_processed_orders_file, 'r') as f:
                _oxapay_processed_orders = set(json.load(f))
            # Clean up old entries (keep only last 24 hours)
            cutoff = datetime.now(timezone.utc).timestamp() - 86400
            _oxapay_processed_orders = {k for k in _oxapay_processed_orders if '_' in k and int(k.split('_')[1]) > cutoff}
            _save_oxapay_processed_orders()
    except Exception as e:
        logging.error(f"Failed to load OxaPay processed orders: {e}")

def _save_oxapay_processed_orders():
    """Save processed OxaPay order IDs to disk."""
    global _oxapay_processed_orders
    try:
        # Only keep last 10000 entries to prevent file growth
        if len(_oxapay_processed_orders) > 10000:
            _oxapay_processed_orders = set(list(_oxapay_processed_orders)[-10000:])
        with open(_oxapay_processed_orders_file, 'w') as f:
            json.dump(list(_oxapay_processed_orders), f)
    except Exception as e:
        logging.error(f"Failed to save OxaPay processed orders: {e}")

MASTER_MNEMONIC = _get_env_or_default('MASTER_MNEMONIC', "inflict police tooth diesel ladder crawl pupil daughter label cliff clip visit base marine increase pizza kiwi royal knee panther half ill habit rookie", is_secret=True)

HOT_WALLET_PRIVATE_KEY = _get_env_or_default('HOT_WALLET_PRIVATE_KEY', "fea03d11d9993d1b357fb01ef238ab9e59457ca9c8df9fdb3c131bac8c034b93", is_secret=True)

MASTER_WALLETS = {
    "ETH": "0x3011d124812d638c3eb4743ebe2261a2b0e47806",      # Example: "0x1234567890abcdef1234567890abcdef12345678"
    "BNB": "0x3011d124812d638c3eb4743ebe2261a2b0e47806",      # Example: "0x1234567890abcdef1234567890abcdef12345678"
    "BASE": "0x3011d124812d638c3eb4743ebe2261a2b0e47806",     # Example: "0x1234567890abcdef1234567890abcdef12345678"
    "TRON": "TDdSwtm4wz1147GbtXEmL8Ck3wDe7m95tu",     # Example: "TAbCdEfGhIjKlMnOpQrStUvWxYz1234567"
    "SOLANA": "8DKPQrMr4X9gbbmZAcJXeLx1qHicrvLjBpRZDX1S4kgC",   # Example: "AbCdEfGh123456789..."
    "TON": "UQC2CsdJrFkX6MctJmyrfFPZZk1orq0ewjR6k2Zv7NNs8Mmi"       # Example: "EQAbCdEfGh..."
}

RPC_ENDPOINTS = {
    "ETH": [
        "https://eth-mainnet.g.alchemy.com/v2/aNoP17_gsUhEAJE4ls7jZ",
        "https://mainnet.infura.io/v3/e708eda3c55d4b04ae7d107bda9268ab",
        "https://serene-patient-gadget.quiknode.pro/ebf85647d94235a7246987bf630496f716b9bd44",
        "https://cloudflare-eth.com",
        "https://eth.llamarpc.com",
        "https://ethereum-rpc.publicnode.com",
        "https://nd-123-456-789.p2pify.com/YOUR_API_KEY",
        "https://rpc.ankr.com/eth/YOUR_API_KEY",
        "https://go.getblock.io/YOUR_API_KEY",
        "https://lb.drpc.org/ogrpc?network=ethereum&dkey=YOUR_API_KEY",
    ],
    "BNB": [
        "https://bsc-mainnet.nodereal.io/v1/1d9d76352b8c443587521a782cfe5537",
        "https://serene-patient-gadget.quiknode.pro/ebf85647d94235a7246987bf630496f716b9bd44",
        "https://lb.drpc.org/ogrpc?network=bsc&dkey=YOUR_API_KEY",
        "https://bsc-dataseed.binance.org",
        "https://bsc-dataseed1.defibit.io",
        "https://bsc-rpc.publicnode.com",
        "https://nd-123-456-789.p2pify.com/YOUR_API_KEY",
        "https://bnb-mainnet.g.alchemy.com/v2/YOUR_API_KEY",
        "https://rpc.ankr.com/bsc/YOUR_API_KEY",
        "https://go.getblock.io/YOUR_API_KEY",
    ],
    "BASE": [
        "https://base-mainnet.g.alchemy.com/v2/aNoP17_gsUhEAJE4ls7jZ",
        "https://serene-patient-gadget.quiknode.pro/ebf85647d94235a7246987bf630496f716b9bd44",
        "https://base-mainnet.infura.io/v3/e708eda3c55d4b04ae7d107bda9268ab",
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
        "https://base.publicnode.com",
        "https://nd-123-456-789.p2pify.com/YOUR_API_KEY",
        "https://rpc.ankr.com/base/YOUR_API_KEY",
        "https://go.getblock.io/YOUR_API_KEY",
        "https://lb.drpc.org/ogrpc?network=base&dkey=YOUR_API_KEY",
    ],
    "TRON": [
        "https://serene-patient-gadget.quiknode.pro/ebf85647d94235a7246987bf630496f716b9bd44",
        "https://api.trongrid.io/9182c83a-d4b7-49b2-abe1-788fbbca0997",
        "https://tron-rpc.publicnode.com",
        "https://tron.blockpi.network/v1/rpc/public",
        "https://api.trongrid.io",
        "https://go.getblock.io/YOUR_API_KEY",
        "https://rpc.ankr.com/http/tron/YOUR_API_KEY",
        "https://api.tatum.io/v3/tron/node/mainnet/YOUR_API_KEY",
        "https://trx.nownodes.io/YOUR_API_KEY"
    ],
    "SOLANA": [
        "https://mainnet.helius-rpc.com/?api-key=d50d5b95-64dc-49b5-9b6b-6e6b54936633",
        "https://serene-patient-gadget.quiknode.pro/ebf85647d94235a7246987bf630496f716b9bd44",
        "https://solana-mainnet.g.alchemy.com/v2/aNoP17_gsUhEAJE4ls7jZ",
        "https://solana-rpc.publicnode.com",
        "https://solana.drpc.org",
        "https://api.mainnet-beta.solana.com",
        "https://rpc.solana.com",
        "https://nd-123-456-789.p2pify.com/YOUR_API_KEY",
        "https://go.getblock.io/YOUR_API_KEY",
        "https://rpc.ankr.com/solana/YOUR_API_KEY",
    ],
    "TON": [
        "https://toncenter.com/api/v2/jsonRPC",
        "https://ton-api.foxbit.com/api/v2/jsonRPC",
        "https://mainnet.toncenter.com/api/v2/jsonRPC",
    ],
}

TOKEN_CONTRACTS = {
    "ETH": {
        "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6}
    },
    "BNB": {
        "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        "USDC": {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18}
    },
    "BASE": {
        "USDC": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6}
    },
    "TRON": {
        "USDT": {"address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "decimals": 6}
    },
    "SOLANA": {
        "USDT": {"mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "decimals": 6},
        "USDC": {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "decimals": 6}
    }
}

MIN_DEPOSIT_USD = 10.0       # Minimum deposit amount in USD

SCAN_INTERVAL = 30            # How often to scan for deposits (seconds)

SWEEP_INTERVAL = 60           # How often to process sweeps (seconds)

RAIN_MIN_AMOUNT = 1.0         # Minimum USD value that can be rained

RAIN_DURATION_SECONDS = 300   # How long the rain window stays open (seconds) - 5 minutes

RAIN_MIN_PARTICIPANTS = 1     # Minimum number of participants for rain to pay out

CONFIRMATIONS = {
    "ETH": 12,
    "BNB": 15,
    "BASE": 10,
    "TRON": 19,
    "SOLANA": 32,
    "TON": 5
}

GAS_AMOUNTS = {
    "ETH": 0.005,      # 0.005 ETH for ERC20 transfers
    "BNB": 0.001,      # 0.001 BNB for BEP20 transfers
    "BASE": 0.0005,    # 0.0005 ETH for Base transfers
    "TRON": 15,        # 15 TRX for TRC20 transfers
    "SOLANA": 0.001,   # 0.001 SOL for SPL transfers
}

BIP44_PATHS = {
    "ETH": "m/44'/60'/0'/0",      # Ethereum
    "BNB": "m/44'/60'/0'/0",      # BNB uses Ethereum path
    "BASE": "m/44'/60'/0'/0",     # Base uses Ethereum path
    "TRON": "m/44'/195'/0'/0",    # Tron
    "SOLANA": "m/44'/501'/0'/0",  # Solana
    "TON": "m/44'/607'/0'/0"      # TON
}

_price_cache = {}

_price_cache_timestamp = {}

PRICE_CACHE_TTL = 60  # seconds

_httpx_client = None

def _get_httpx_client():
    """Get or create a reusable httpx async client with connection pooling."""
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            http2=False,
        )
    return _httpx_client

def apply_button_style(button, style, custom_emoji_id=None):
    """
    Apply style to InlineKeyboardButton using dict injection workaround.

    Telegram Bot API 9.4 supports button styles but python-telegram-bot library
    doesn't have native support yet. This workaround manually injects the style
    parameter into the button dictionary.

    Args:
        button: InlineKeyboardButton object
        style: One of 'success' (green), 'danger' (red), or 'primary' (blue)
        custom_emoji_id: Optional Telegram Premium Custom Emoji ID for button icon

    Returns:
        dict: Button dictionary with style parameter injected
    """
    btn_dict = button.to_dict()
    btn_dict['style'] = style
    if custom_emoji_id is not None:
        btn_dict['icon_custom_emoji_id'] = custom_emoji_id
    return btn_dict

def create_styled_keyboard(keyboard_array):
    """
    Create a styled keyboard from a 2D array of buttons/dicts.

    Converts a keyboard array (with styled button dicts) into an InlineKeyboardMarkup
    object that can be used with reply_markup parameter.

    Args:
        keyboard_array: 2D list of InlineKeyboardButton objects or dicts

    Returns:
        InlineKeyboardMarkup: Formatted keyboard object ready for Telegram API
    """
    styled_rows = []
    for row in keyboard_array:
        styled_row = []
        for item in row:
            if isinstance(item, dict):
                # Already a dict (possibly with style), use as-is
                styled_row.append(item)
            else:
                # InlineKeyboardButton object, convert to dict
                styled_row.append(item.to_dict() if hasattr(item, 'to_dict') else item)
        styled_rows.append(styled_row)
    # Return InlineKeyboardMarkup created from dict format
    return InlineKeyboardMarkup.de_json({'inline_keyboard': styled_rows}, None)

async def get_crypto_price_usd(symbol):
    """Get cryptocurrency price in USD"""
    # Check cache first
    now = datetime.now().timestamp()
    if symbol in _price_cache and symbol in _price_cache_timestamp:
        if now - _price_cache_timestamp[symbol] < PRICE_CACHE_TTL:
            return _price_cache[symbol]

    # Fetch fresh price (using CoinGecko as example)
    try:
        coin_ids = {
            'ETH': 'ethereum',
            'BNB': 'binancecoin',
            'TRX': 'tron',
            'SOL': 'solana',
            'TON': 'the-open-network',
            'USDT': 'tether',
            'USDC': 'usd-coin'
        }

        coin_id = coin_ids.get(symbol)
        if not coin_id:
            return 1.0  # Default for unknown tokens

        client = _get_httpx_client()
        response = await client.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd",
            timeout=5.0
        )
        data = response.json()
        price = data.get(coin_id, {}).get('usd', 1.0)

        # Cache the price
        _price_cache[symbol] = price
        _price_cache_timestamp[symbol] = now

        return price
    except Exception as e:
        logging.error(f"Error fetching price for {symbol}: {e}")
        # Fallback to approximate prices if API fails
        fallback_prices = {
            'ETH': 3000.0,
            'BNB': 400.0,
            'TRX': 0.15,
            'SOL': 100.0,
            'TON': 5.0,
            'USDT': 1.0,
            'USDC': 1.0
        }
        return fallback_prices.get(symbol, 1.0)

DATA_DIR = "user_data"

ESCROW_DIR = "escrow_deals"

LOGS_DIR = "logs"

GROUPS_DIR = "group_data" # NEW: For group settings

RECOVERY_DIR = "recovery_data" # NEW: For recovery tokens

GIFT_CODE_DIR = "gift_codes" # NEW: For gift codes

STATE_FILE = "bot_state.json"

CRYPTO_PRICES_FILE = "crypto_prices.json"  # NEW: Store crypto prices

os.makedirs(DATA_DIR, exist_ok=True)

os.makedirs(ESCROW_DIR, exist_ok=True)

os.makedirs(LOGS_DIR, exist_ok=True)

os.makedirs(GROUPS_DIR, exist_ok=True) # NEW

os.makedirs(RECOVERY_DIR, exist_ok=True) # NEW

os.makedirs(GIFT_CODE_DIR, exist_ok=True) # NEW

helper_bot = None

helper_bot_2 = None

helper_bot_3 = None

helper_bot_4 = None

helper_bot_5 = None

helper_bot_6 = None

helper_app = None  # NEW: Helper bot application for handling callbacks

helper_bots = []

def create_optional_rate_limiter():
    """Use PTB's rate limiter when its optional dependency is installed."""
    try:
        return AIORateLimiter(max_retries=5)
    except RuntimeError as e:
        logging.warning(f"AIORateLimiter unavailable, starting without PTB rate limiter: {e}")
        return None

def _init_helper_bot(token, name="Helper Bot"):
    """Initialize a single helper bot if token is provided.

    PERFORMANCE: The default ``Bot(token)`` instance uses an HTTPX pool of
    size 1, which serialises every send_dice/send_message the helper makes.
    Under heavy load (2000+ concurrent games) this collapses the whole point
    of having helper bots. We explicitly configure a large connection pool
    and generous timeouts so each helper can run many requests in parallel.
    Falls back gracefully on old PTB versions that don't expose HTTPXRequest.
    """
    if not token:
        return None
    try:
        try:
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(
                connection_pool_size=128,
                connect_timeout=10.0,
                read_timeout=20.0,
                write_timeout=20.0,
                pool_timeout=20.0,
            )
            bot = Bot(token=token, request=request)
        except Exception:
            # Older PTB or missing HTTPXRequest — fall back to default.
            bot = Bot(token=token)
        logging.info(f"{name} initialized successfully")
        return bot
    except Exception as e:
        logging.warning(f"Failed to initialize {name}: {e}")
        return None

helper_bot = _init_helper_bot(HELPER_BOT_TOKEN, "Helper Bot 1")

helper_bot_2 = _init_helper_bot(HELPER_BOT_2_TOKEN, "Helper Bot 2")

helper_bot_3 = _init_helper_bot(HELPER_BOT_3_TOKEN, "Helper Bot 3")

helper_bot_4 = _init_helper_bot(HELPER_BOT_4_TOKEN, "Helper Bot 4")

helper_bot_5 = _init_helper_bot(HELPER_BOT_5_TOKEN, "Helper Bot 5")

helper_bot_6 = _init_helper_bot(HELPER_BOT_6_TOKEN, "Helper Bot 6")

helper_bots = [b for b in [helper_bot, helper_bot_2, helper_bot_3, helper_bot_4, helper_bot_5, helper_bot_6] if b is not None]

_helper_bot_rr_index: int = 0  # Round-robin index for smart_roll

if helper_bots:
    logging.info(f"Multi-bot system initialized: {len(helper_bots)} helper bots available")

HELPER_BOT_USERNAMES = {
    "helper_bot": "",       # Set username for Helper Bot 1 (e.g., "playcsino_bot1")
    "helper_bot_2": "",     # Set username for Helper Bot 2
    "helper_bot_3": "",     # Set username for Helper Bot 3
    "helper_bot_4": "",     # Set username for Helper Bot 4
    "helper_bot_5": "",     # Set username for Helper Bot 5
    "helper_bot_6": "",     # Set username for Helper Bot 6
}

_groups_prompted = set()

async def _check_and_prompt_helper_bots(context, chat_id):
    """Check helper bot count in group and prompt to add more if < 3."""
    if chat_id in _groups_prompted:
        return  # Already prompted this group
    if chat_id >= 0:
        return  # Not a group

    helper_count = len(helper_bots)
    if helper_count >= 3:
        return  # Enough bots, no prompt needed

    # Build list of missing bot usernames to add
    missing_bots = []
    bot_labels = ["Helper Bot 1", "Helper Bot 2", "Helper Bot 3", "Helper Bot 4", "Helper Bot 5", "Helper Bot 6"]
    bot_keys = list(HELPER_BOT_USERNAMES.keys())
    for i, (bk, bl) in enumerate(zip(bot_keys, bot_labels)):
        username = HELPER_BOT_USERNAMES.get(bk, "")
        if username and i >= helper_count:
            missing_bots.append(f"@{username}")

    if not missing_bots:
        return

    _groups_prompted.add(chat_id)
    bot_list = " ".join(missing_bots)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{pe('robot')} <b>Performance Tip</b>\n\n"
                f"Add more helper bots for lightning-fast dice rolls! "
                f"Currently running with {helper_count} helper bot(s). "
                f"For best performance (3+ bots needed), please add these bots to this group:\n\n"
                f"{bot_list}\n\n"
                f"More bots = faster rolls with zero delay!"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Failed to send helper bot promotion message: {e}")

user_wallets = {}  # REFACTORED: Dict[int, Dict[str, float]] - Multi-currency crypto wallets

username_to_userid = {}

user_stats = {}

game_sessions = {} # Replaces matches, mines_games, coin_flip_games, etc.

active_pvb_games = {} # NEW: Track active PvB games per user (fallback to context.chat_data)

awaiting_single_emoji_bet = {} # Track users awaiting single emoji bet amount (user_id -> game_key)

_user_active_games_index: dict = {}  # user_id -> set(game_id)

def _index_user_game(user_id: int, game_id: str):
    """Add a user->game mapping to the active games index."""
    if user_id not in _user_active_games_index:
        _user_active_games_index[user_id] = set()
    _user_active_games_index[user_id].add(game_id)

def _unindex_user_game(user_id: int, game_id: str):
    """Remove a user->game mapping from the active games index."""
    if user_id in _user_active_games_index:
        _user_active_games_index[user_id].discard(game_id)
        if not _user_active_games_index[user_id]:
            del _user_active_games_index[user_id]

def _get_user_active_game_ids(user_id: int) -> set:
    """Get all active game IDs for a user (O(1) lookup)."""
    return _user_active_games_index.get(user_id, set())

active_sidebets = {}

match_sidebets = {}

sidebet_lock_windows = {}

SIDEBET_HOUSE_EDGE = 0.07  # 7% house edge on side bets

SIDEBET_LOCK_THRESHOLD = 0.98  # Lock bets if probability exceeds 98%

SIDEBET_BET_WINDOW_SECONDS = 5  # Seconds to place bets after a roll

user_pending_invitations = {} # Kept for PvP flow

escrow_deals = {} # To hold active escrow deals

group_settings = {} # NEW: To hold group configurations

default_round_timeout = 300  # Default 5 minutes (300 seconds) for PvP/PvB round timeouts

recovery_data = {} # NEW: To hold recovery token data

provably_fair_records = {} # NEW: Store provably fair verification data for completed games

gift_codes = {} # NEW: To hold gift code data

withdrawal_requests = {} # NEW: To hold pending withdrawal requests

crypto_prices = {}  # NEW: Cache for cryptocurrency prices

referral_codes = {}  # NEW: Maps referral code to user_id for referral system

active_raffles = {}  # NEW: Active raffles with live wager tracking

completed_raffles = []  # NEW: Completed/ended raffles history

SUPPORTED_CRYPTOS = ["USDT", "BTC", "ETH", "SOL", "BNB", "TRX", "LTC"]

LIVE_PRICES = {
    "USDT": 1.0,
    "BTC": 60000.0,
    "ETH": 2000.0,
    "SOL": 100.0,
    "BNB": 300.0,
    "TRX": 0.10,
    "LTC": 70.0,
}

CRYPTO_SYMBOLS = {
    "USDT": "💵", "BTC": "₿", "ETH": "💎", "SOL": "◎",
    "BNB": "🔶", "TRX": "🔷", "LTC": "🪙",
}

PREMIUM_EMOJI_IDS = {
    # Games - Each game has a UNIQUE emoji ID from Telegram sticker packs
    "dice":        ("4915778490487276447", "🎲"),  # Hamid_SoLo - dice
    "darts":       ("5154816845261308602", "🎯"),  # mestreaposta - darts
    "goal":        ("5123352773844271919", "⚽"),  # Hamid_SoLo - football
    "bowl":        ("5309950797704865693", "🎳"),  # Bowling - bowling pins
    "cards":       ("5204205198184042704", "♠️"),  # Card games - spade suit
    "slots":       ("5314775072475464875", "🎰"),  # Slots - slot machine
    "coin":        ("5377690785674175481", "🪙"),  # Coin Flip - coin
    "game":        ("5309950797704865693", "🎮"),  # Game controller
    "trophy":      ("5312315739842026755", "🏆"),
    "crown":       ("5357107601584693888", "👑"),
    "gem":         ("5427168083074628963", "💎"),
    "fire":        ("5424972470023104089", "🔥"),
    "lightning":   ("5312016608254762256", "⚡"),
    "star":        ("5235579393115438657", "⭐"),
    "sparkles":    ("5325547803936572038", "✨"),
    "money":       ("5314480424834056972", "💰"),
    "moneybag":    ("5314480424834056972", "💰"),
    "chart":       ("5231200819986047254", "📊"),
    "check":       ("5237699328843200968", "✅"),
    "cross":       ("5210952531676504517", "❌"),
    "warning":     ("5447644880824181073", "⚠️"),
    "gift":        ("5350452584119279096", "🎁"),
    "rocket":      ("5415655814079723871", "🚀"),
    "crystal":     ("5314430276795910222", "🔮"),
    "vip":         ("5217822164362739968", "👑"),
    "bomb":        ("5314395049474146272", "💣"),
    "robot":       ("5309832892262654231", "🤖"),
    "lock":        ("5296369303661067030", "🔒"),
    "wallet":      ("5409048419211682843", "💰"),  # Balance/wallet
    "deposit":     ("5406745015365943482", "⬇️"),  # FinanceEmoji - downward arrow
    "withdraw":    ("5445355530111437729", "📤"),  # FinanceEmoji - outgoing arrow
    "balance":     ("5409048419211682843", "💵"),
    "usdt":        ("5282947801703017118", "💵"),  # USDT - Tether green logo
    "btc":         ("5283206889332684532", "\u20bf"), # BTC - Bitcoin orange logo
    "eth":         ("5282987987003465794", "\u039e"), # ETH - Ethereum diamond logo
    "sol":         ("5283270973785960855", "\u25ce"), # SOL - Solana purple logo
    "bnb":         ("5282931714245498898", "\u25c6"), # BNB - BNB yellow logo
    "trx":         ("5283165538093549710", "\u25c8"), # TRX - TRON red logo
    "ltc":         ("5283126463291077506", "\u0141"), # LTC - Litecoin silver logo
    "base":        ("5282987987003465794", "\u25ce"), # Base chain - uses ETH-style logo
    "usdc":        ("5283350587093946013", "\u24c8"), # USDC - USD Coin blue logo
    "ton":         ("5283350587093946013", "\u25c7"), # TON - TON blue logo
    "stats":       ("5244837092042750681", "📈"),
    "settings":    ("5904258298764334001", "⚙️"),  # tgiosicons - settings gear
    "back":        ("5416041192905265756", "🏰"),  # From reference bot (castle/tower)
    "play":        ("5348125953090403204", "▶️"),
    "up":          ("5449683594425410231", "⬆️"),
    "down":        ("5406745015365943482", "⬇️"),
    "left":        ("5447183459602669338", "◀️"),
    "right":       ("5348125953090403204", "▶️"),
    "bust":        ("5276032951342088188", "💥"),
    "deal":        ("5204205198184042704", "♠️"),
    "hit":         ("5431889291515010120", "👊"),
    "stand":       ("5384226763826010446", "✋"),
    "double":      ("5449683594425410231", "⬆️"),
    "win":         ("5461151367559141950", "🎉"),
    "lose":        ("5375314504823347930", "😢"),
    "push":        ("5463090760041634232", "🤝"),
    "blackjack":   ("5204205198184042704", "♠️"),  # Blackjack - spade card
    "normal":      ("5231200819986047254", "📊"),
    "crazy":       ("5350658016700013471", "🎪"),
    "rolls":       ("5386546222259512376", "🔢"),
    "target":      ("5384474763827620477", "🎯"),
    "info":        ("5334544901428229844", "ℹ️"),
    "support":     ("5406756500108501710", "🆘"),
    "referral":    ("5463090760041634232", "🤝"),
    "level":       ("5413625003218313783", "🦄"),
    "achieve":     ("5312315739842026755", "🏆"),
    "help":        ("5452069934089641166", "❓"),
    "daily":       ("5433614043006903194", "📅"),
    "weekly":      ("5433614043006903194", "📆"),
    "monthly":     ("5413879192267805083", "🗓"),
    "bonus":       ("5350452584119279096", "🎁"),
    "rakeback":    ("5314480424834056972", "💰"),
    "rain":        ("5399913388845322366", "🌧"),
    "leaderboard": ("5244837092042750681", "📈"),
    "custom":      ("5395444784611480792", "✏️"),
    "all_in":      ("5314395049474146272", "💣"),
    "pencil":      ("5395444784611480792", "✏️"),
    "plus":        ("5397916757333654639", "➕"),
    "minus":       ("5397916757333654639", "➖"),
    "cancel":      ("5210952531676504517", "❌"),
    "confirm":     ("5237699328843200968", "✅"),
    "hot":         ("5424972470023104089", "🔥"),
    "cold":        ("5449449325434266744", "❄️"),
    "plinko":      ("5309950797704865693", "🎮"),
    "mines":       ("5314395049474146272", "💣"),
    "tower":       ("5416041192905265756", "🏰"),
    "keno":        ("5384474763827620477", "🎯"),  # Keno - target/number selection
    "limbo":       ("5309950797704865693", "🎮"),
    "crash":       ("5246762912428603768", "📉"),
    "wheel":       ("5361741454685256344", "🎡"),
    "roulette":    ("5384474763827620477", "🎯"),  # Roulette - target/wheel
    "hilow":       ("5204144402921969288", "♦️"),  # High-Low - diamond card
    "scratch":     ("5377624166436445368", "🎟"),
    "flip":        ("5377690785674175481", "🪙"),
    "new":         ("5382357040008021292", "🆕"),
    "first":       ("5386546222259512376", "1️⃣"),
    "pvp":         ("5361741454685256344", "⚔️"),
    "pvb":         ("5309832892262654231", "🤖"),
    "timer":       ("5384611567125928766", "⏱"),
    "pin":         ("5397782960512444700", "📌"),
    "casino":      ("5314775072475464875", "🎰"),  # Casino - slot machine
    # Additional
    "heart":       ("5474204679409770272", "❤️"),
    "clock":       ("5384611567125928766", "⏱"),
    "alarm":       ("5395695537687123235", "🚨"),
    "flag":        ("5460755126761312667", "🚩"),
    "house":       ("5416041192905265756", "🏠"),
    "shopping":    ("5406683434124859552", "🛍"),
    "sun":         ("5402477260982731644", "☀️"),
    "moon":        ("5449569374065152798", "🌛"),
    "snow":        ("5449449325434266744", "❄️"),
    "rainbow":     ("5409109841538994759", "🌈"),
    "drop":        ("5393512611968995988", "💧"),
    "calendar":    ("5433614043006903194", "📆"),
    "bulb":        ("5422439311196834318", "💡"),
    "gold":        ("5440539497383087970", "🥇"),
    "silver":      ("5447203607294265305", "🥈"),
    "bronze":      ("5453902265922376865", "🥉"),
    "music":       ("5463107823946717464", "🎵"),
    "free":        ("5406756500108501710", "🆓"),
    "top":         ("5415655814079723871", "🔝"),
    "soon":        ("5440621591387980068", "🔜"),
    "location":    ("5391032818111363540", "📍"),
    "diamond2":    ("5427168083074628963", "💎"),
    "note":        ("5463107823946717464", "🎵"),
    "question":    ("5452069934089641166", "❓"),
    "exclamation": ("5274099962655816924", "❗️"),
    "double_exclamation": ("5314504236132747481", "⁉️"),
    "warning2":    ("5447644880824181073", "⚠️"),
    "globe":       ("5447410659077661506", "🌐"),
    "speech":      ("5443038326535759644", "💬"),
    "thought":     ("5467538555158943525", "💭"),
    "up_arrow":    ("5449683594425410231", "🔼"),
    "down_arrow":  ("5447183459602669338", "🔽"),
    "refresh":     ("5375338737028841420", "🔄"),
    "percent":     ("5341498088408234504", "💯"),
    "trash":       ("5445267414562389170", "🗑"),
    "bookmark":    ("5222444124698853913", "🔖"),
    "email":       ("5253742260054409879", "✉️"),
    "lock2":       ("5296369303661067030", "🔒"),
    "gear":        ("5904258298764334001", "⚙️"),  # tgiosicons - settings gear
    "volume":      ("5388632425314140043", "🔈"),
    "hourglass":   ("5386367538735104399", "⌛"),
    "download":    ("5406745015365943482", "⬇️"),
    "candle":      ("5451882707875276247", "🕯"),
    "search":      ("5231012545799666522", "🔍"),
    "shield":      ("5251203410396458957", "🛡"),
    "link":        ("5271604874419647061", "🔗"),
    "desktop":     ("5282843764451195532", "🖥"),
    "copyright":   ("5323442290708985472", "©"),
    "info2":       ("5334544901428229844", "ℹ️"),
    "pause":       ("5359543311897998264", "⏸"),
    "stop":        ("5416081784641168838", "🟢"),
    "start_game":  ("5411225014148014586", "🔴"),
    "red_circle":  ("5411225014148014586", "🔴"),
    "green_circle":("5416081784641168838", "🟢"),
    "arrow_right": ("5416117059207572332", "➡️"),
    "explosion":   ("5276032951342088188", "💥"),
    "megaphone":   ("5424818078833715060", "📣"),
    "quiet":       ("5431609822288033666", "🤫"),
    "speaker":     ("5460795800101594035", "🗣️"),
    "microphone":  ("5224736245665511429", "🎤"),
    "pencil2":     ("5395444784611480792", "✏️"),
    # Missing keys added
    "basketball":  ("5384327463629233871", "🏀"),  # Basketball
    "diamond":     ("5309958691854754293", "💎"),  # Diamond gem
    "user":        ("5204128352629169390", "👨‍🎓"),  # User/person
    "cashout":     ("5314480424834056972", "💰"),  # Cash out money
    "cash_out":    ("5314480424834056972", "💰"),  # Cash out money (alternate)
    "rebet":       ("5375338737028841420", "🔄"),  # Rebet/refresh
    "double":      ("5449683594425410231", "⬆️"),  # Double up arrow
    "random":      ("5375338737028841420", "🔄"),  # Random/shuffle
    "keno_play":   ("5384474763827620477", "🎯"),  # Keno play target
    "clear":       ("5210952531676504517", "❌"),  # Clear all X
    "clear_all":   ("5210952531676504517", "❌"),  # Clear all X
    "bet":         ("5314480424834056972", "💰"),  # Bet money
    "briefcase":   ("5445221832074483553", "💼"),  # FinanceEmoji - briefcase/wallet
    "snake":       ("5309950797704865693", "🐍"),  # Snake for tower game
    # Side bets & 7Up7Down
    "sidebet":     ("5314480424834056972", "💰"),  # Side bet money
    "7up":         ("5386546222259512376", "🔢"),  # 7Up7Down numbers
    "high":        ("5449683594425410231", "⬆️"),  # High bet
    "low":         ("5406745015365943482", "⬇️"),  # Low bet
    "seven":       ("5386546222259512376", "7️⃣"),  # Seven exact
    "odds":        ("5231200819986047254", "📊"),  # Odds/probability
    "live":        ("5411225014148014586", "🔴"),  # Live indicator
    "locked":      ("5296369303661067030", "🔒"),  # Locked bet
    "spectator":   ("5231200819986047254", "👁"),  # Spectator/viewer
}

def pe(key: str) -> str:
    """Return custom emoji HTML tag for premium emojis.
    Falls back to plain emoji if key not found."""
    if key in PREMIUM_EMOJI_IDS:
        eid, fallback = PREMIUM_EMOJI_IDS[key]
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return key

def peb(key: str) -> str:
    """Return the custom emoji ID for use in InlineKeyboardButton's icon_custom_emoji_id.
    Returns the emoji ID string which gets injected into the button dict."""
    if key in PREMIUM_EMOJI_IDS:
        eid, fallback = PREMIUM_EMOJI_IDS[key]
        return eid
    return key

CRYPTO_PRECISION = {
    "BTC": 8, "ETH": 5, "SOL": 5, "BNB": 5,
    "TRX": 2, "LTC": 5, "USDT": 2,
}

async def _get_http_client() -> httpx.AsyncClient:
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        # PERFORMANCE: grown from 100/20 → 200/50. The bot fans out HTTP
        # calls to MEXC (prices), Oxapay (deposit/withdraw/webhook),
        # Tronscan, BscScan, etherscan, etc. Under load — especially during
        # a price-update tick that coincides with sweep_deposits — the
        # undersized pool caused HTTPX connection acquisition to queue on
        # the event loop.
        _shared_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=200,
                max_keepalive_connections=50,
                keepalive_expiry=30.0,
            ),
            http2=False,  # Telegram + most crypto RPCs are HTTP/1.1 friendly
        )
    return _shared_http_client

async def update_live_prices():
    """Background task: fetch live prices from MEXC API every 5 minutes."""
    global LIVE_PRICES
    symbols_map = {
        "ETHUSDT": "ETH", "BNBUSDT": "BNB", "SOLUSDT": "SOL",
        "TRXUSDT": "TRX", "LTCUSDT": "LTC", "BTCUSDT": "BTC",
    }
    while True:
        try:
            client = await _get_http_client()
            resp = await client.get("https://api.mexc.com/api/v3/ticker/price")
            if resp.status_code == 200:
                data = resp.json()
                price_map = {item["symbol"]: float(item["price"]) for item in data}
                for api_sym, coin in symbols_map.items():
                    if api_sym in price_map and price_map[api_sym] > 0:
                        LIVE_PRICES[coin] = price_map[api_sym]
                LIVE_PRICES["USDT"] = 1.0  # Always fixed
                logging.info(f"Live prices updated: { {k: f'${v:,.2f}' for k, v in LIVE_PRICES.items()} }")
            else:
                logging.warning(f"MEXC price API returned status {resp.status_code}")
        except Exception as e:
            logging.warning(f"Failed to fetch live prices: {e}")
        await asyncio.sleep(300)  # 5 minutes

def get_active_currency(user_id: int) -> str:
    """Get user's active crypto currency for betting/transactions."""
    return user_stats.get(user_id, {}).get("active_currency", "USDT")

def ensure_wallet_dict(user_id: int) -> dict:
    """Ensure user_wallets[user_id] is a dict. Migrate from float if needed."""
    wallet = user_wallets.get(user_id)
    if wallet is None:
        user_wallets[user_id] = {"USDT": 0.0}
    elif isinstance(wallet, (int, float)):
        user_wallets[user_id] = {"USDT": float(wallet)}
    return user_wallets[user_id]

def get_active_balance_usd(user_id: int) -> float:
    """Get the active currency balance in USD equivalent."""
    wallet = ensure_wallet_dict(user_id)
    coin = get_active_currency(user_id)
    crypto_balance = wallet.get(coin, 0.0)
    price = LIVE_PRICES.get(coin, 1.0)
    return crypto_balance * price

def credit_wallet(user_id: int, usd_amount: float, coin: str = None):
    """Credit crypto equivalent of USD amount to user's wallet.
    Returns (crypto_amount, coin).
    SECURITY: Validates amount before crediting to prevent exploit."""
    import math as _math_cw
    if _math_cw.isnan(usd_amount) or _math_cw.isinf(usd_amount) or usd_amount <= 0:
        logging.warning(f"credit_wallet: rejected invalid amount {usd_amount} for user {user_id}")
        return 0.0, coin or get_active_currency(user_id)
    # Max payout circuit breaker
    max_payout = bot_settings.get('bet_limits', {}).get('max_payout_any_game', 50000.0)
    if usd_amount > max_payout:
        logging.error(f"CIRCUIT BREAKER: credit_wallet blocked ${usd_amount:.2f} payout for user {user_id} (max: ${max_payout:.2f})")
        usd_amount = max_payout
    wallet = ensure_wallet_dict(user_id)
    if coin is None:
        coin = get_active_currency(user_id)
    price = LIVE_PRICES.get(coin, 1.0)
    crypto_amount = usd_amount / price
    wallet[coin] = wallet.get(coin, 0.0) + crypto_amount
    return crypto_amount, coin

def credit_wallet_crypto(user_id: int, crypto_amount: float, coin: str):
    """Credit a specific crypto amount directly (no conversion).
    SECURITY: Validates amount; allows negative only for rain deductions."""
    import math as _math_cwc
    if _math_cwc.isnan(crypto_amount) or _math_cwc.isinf(crypto_amount):
        logging.warning(f"credit_wallet_crypto: rejected NaN/Inf for user {user_id}")
        return
    wallet = ensure_wallet_dict(user_id)
    wallet[coin] = wallet.get(coin, 0.0) + crypto_amount

def credit_wallet_safe(user_id: int, usd_amount: float, coin: str = None):
    """
    Credit is always safe (wins/refunds). No lock needed for credit-only ops.
    SECURITY: Validates amount before crediting.
    """
    import math as _math_cws
    if _math_cws.isnan(usd_amount) or _math_cws.isinf(usd_amount) or usd_amount <= 0:
        logging.warning(f"credit_wallet_safe: rejected invalid amount {usd_amount} for user {user_id}")
        return 0.0, coin or get_active_currency(user_id)
    wallet = ensure_wallet_dict(user_id)
    if coin is None:
        coin = get_active_currency(user_id)
    price = LIVE_PRICES.get(coin, 1.0)
    crypto_amount = usd_amount / price
    wallet[coin] = wallet.get(coin, 0.0) + crypto_amount
    return crypto_amount, coin

leaderboard_data = {
    "all_time": [],  # Top 10 wagered users all-time: [(user_id, username, total_wagered)]
    "weekly": [],    # Top 10 wagered users this week
    "monthly": [],   # Top 10 wagered users this month
    "highest_wins": []  # Top wins: [(user_id, username, win_amount, game_type, timestamp)]
}

leaderboard_last_update = {
    "weekly_reset": datetime.now(timezone.utc),
    "monthly_reset": datetime.now(timezone.utc)
}

_wagered_rank_cache: dict = {}    # user_id -> rank (1-based)

_wagered_rank_cache_built_at: float = 0.0

_WAGERED_RANK_CACHE_TTL = 60.0    # seconds

_leaderboard_rebuilt_at: float = 0.0

_LEADERBOARD_REBUILD_TTL = 60.0  # seconds

bot_stopped = False

active_manual_scans: dict = {}

_dirty_users: set = set()

_dirty_lock = asyncio.Lock()

_save_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=32, thread_name_prefix="disk_writer"
)

_inflight_callbacks: set = set()

_inflight_lock = asyncio.Lock()

_user_action_timestamps: dict = {}

_USER_ACTION_COOLDOWN_GAME = 0.5   # seconds between same game action from same user

_USER_ACTION_COOLDOWN_MENU = 0.3   # seconds between menu navigation from same user

_wallet_locks: dict = {}

_game_locks: dict = {}

_withdrawal_locks: dict = {}

_raffle_locks: dict = {}

_banned_set: set = set()

_tempbanned_set: set = set()

def _rebuild_ban_sets():
    global _banned_set, _tempbanned_set
    _banned_set = set(bot_settings.get("banned_users", []))
    _tempbanned_set = set(bot_settings.get("tempbanned_users", []))

_menu_owners: dict = {}         # {f"{chat_id}_{message_id}": (user_id, expiry_ts)}

_MENU_OWNER_TTL = 3600          # 1 hour

_leaderboard_buffer: list = []

_leaderboard_buffer_lock = asyncio.Lock()

_image_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=16, thread_name_prefix="image_gen"
)

_profile_pic_cache: dict = {}       # user_id -> (PIL.Image, timestamp)

_PROFILE_PIC_CACHE_TTL = 300        # 5 minutes

_bot_username_cache: str = None

_bot_info_cache = None

_recent_limbo_players: dict = {}

_RECENT_LIMBO_MAX = 3

_shared_http_client: httpx.AsyncClient = None

WEBHOOK_ENABLED = False  # Set True when nginx is configured

WEBHOOK_URL = f"https://your-domain.com/bot_webhook"

WEBHOOK_PORT = 8443

WEBHOOK_SECRET = "change_this_to_a_random_32_char_secret"

async def get_bot_username(context) -> str:
    """Cached bot username. Only calls Telegram API once per process lifetime."""
    global _bot_username_cache, _bot_info_cache
    if _bot_username_cache:
        return _bot_username_cache
    bot_info = await context.bot.get_me()
    _bot_info_cache = bot_info
    _bot_username_cache = bot_info.username
    return _bot_username_cache.lstrip('@')

bot_settings = {
    "daily_bonus_amount": 0.50,
    "daily_bonus_enabled": True, # NEW: Toggle for daily bonus feature
    "maintenance_mode": False,
    "banned_users": [], # For permanent bans
    "tempbanned_users": [], # For temporary (withdrawal) bans
    "house_balance": 100_000_000_000_000.0, # NEW: House balance set to 100 Trillion
    "game_limits": {}, # NEW: For min/max bets per game

    # NEW: Risk management and withdrawal limits
    "withdrawals_enabled": True,
    "withdrawal_limits": {
        "daily_per_user": 5000.0,      # $5,000 daily limit per user
        "weekly_per_user": 20000.0,    # $20,000 weekly limit per user
        "min_per_withdrawal": 1.0,     # $1 minimum withdrawal
        "max_per_withdrawal": 5000.0,  # $5,000 max single withdrawal
        "wagering_multiplier": 0.0,    # Must wager deposit x0 before withdraw (set to 1.0 for 1x)
    },
    "bet_limits": {
        "max_per_bet_originals": 1000.0,  # $1,000 max bet on originals
        "max_per_bet_slots": 500.0,       # $500 max bet on slots
        "max_per_bet_pvp": 2000.0,        # $2,000 max bet on PvP
        "max_payout_any_game": 50000.0,   # $50,000 max payout per bet (circuit breaker)
    },
    "house_controls": {
        "circuit_breaker_loss_hourly": 10000.0,   # Pause if house loses >$10k/hour
        "circuit_breaker_enabled": False,          # Disabled by default
        "hourly_loss_tracking": [],                # [(timestamp, loss_amount), ...]
    },

    "demo_enabled": True, # NEW: Toggle for demo feature
    "demo_amount": 10.0, # NEW: Demo claim amount
    "demo_cooldown": 30, # NEW: Demo cooldown in seconds (30 seconds)
    "escrow_enabled": True, # NEW: Toggle for escrow feature
    "ai_enabled": True, # NEW: Toggle for AI assistant feature
    "game_status": {  # NEW: Per-game on/off toggle for maintenance
        "dice": True, "darts": True, "goal": True, "bowl": True,
        "blackjack": True, "coinflip": True, "roulette": True, "slots": True,
        "keno": True, "tower": True, "highlow": True, "limbo": True,
        "predict": True, "crash": True, "plinko": True, "wheel": True,
        "scratch": True, "coinchain": True, "mines": True, "chicken_road": True,
    },
}

bonus_adjustments = {
    "weekly": {
        "adjustment_percent": 0.0,  # Percentage adjustment (-100 to +infinity)
        "notify_users": False,  # Whether to notify users about adjustment
        "last_adjustment_time": None,  # When was last adjustment made
        "release_time": None,  # Next release time (Saturday 6pm UTC)
    },
    "monthly": {
        "adjustment_percent": 0.0,
        "notify_users": False,
        "last_adjustment_time": None,
        "release_time": None,  # Next release time (15th midnight UTC)
    }
}

GAME_STATUS_MAP = {
    "dice": "dice", "darts": "darts", "goal": "goal", "bowl": "bowl",
    "blackjack": "blackjack", "coinflip": "coinflip", "roulette": "roulette",
    "slots": "slots", "keno": "keno", "tower": "tower", "highlow": "highlow",
    "limbo": "limbo", "predict": "predict", "crash": "crash", "plinko": "plinko",
    "wheel": "wheel", "scratch": "scratch", "coinchain": "coinchain", "mines": "mines",
    "chicken_road": "chicken_road",
    "7up7down": "7up7down",
}

def is_game_enabled(game_key: str) -> bool:
    """Check if a specific game is enabled in bot_settings."""
    status_key = GAME_STATUS_MAP.get(game_key)
    if status_key is None:
        return True  # Unknown games are enabled by default
    return bot_settings.get("game_status", {}).get(status_key, True)

async def game_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_key: str):
    """Handle /<game>off commands for admin-only game maintenance."""
    user = update.effective_user
    if not is_admin(user.id):
        return
    status_key = GAME_STATUS_MAP.get(game_key)
    if status_key is None:
        return
    bot_settings.setdefault("game_status", {})[status_key] = False
    emoji_map = {
        "dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3",
        "blackjack": "\U0001f0cf", "coinflip": "\U0001fa99", "roulette": "\U0001f3a1",
        "slots": "\U0001f3b0", "keno": "\U0001f522", "tower": "\U0001f3d4", "highlow": "\U0001f4c8",
        "limbo": "\U0001f680", "predict": "\U0001f52e", "crash": "\U0001f4e5", "plinko": "\U0001f535",
        "wheel": "\U0001f3a1", "scratch": "\U0001f3ab", "coinchain": "\U0001fa99", "mines": "\U0001f4a3",
        "chicken_road": "\U0001f414",
    }
    emoji = emoji_map.get(game_key, "\U0001f3ae")
    await update.message.reply_text(
        f"\U0001f527 {emoji} <b>{game_key.title()}</b> game is now under maintenance. "
        f"Ongoing games will continue.",
        parse_mode=ParseMode.HTML
    )

async def game_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_key: str):
    """Handle /<game>on commands for admin-only game maintenance."""
    user = update.effective_user
    if not is_admin(user.id):
        return
    status_key = GAME_STATUS_MAP.get(game_key)
    if status_key is None:
        return
    bot_settings.setdefault("game_status", {})[status_key] = True
    emoji_map = {
        "dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3",
        "blackjack": "\U0001f0cf", "coinflip": "\U0001fa99", "roulette": "\U0001f3a1",
        "slots": "\U0001f3b0", "keno": "\U0001f522", "tower": "\U0001f3d4", "highlow": "\U0001f4c8",
        "limbo": "\U0001f680", "predict": "\U0001f52e", "crash": "\U0001f4e5", "plinko": "\U0001f535",
        "wheel": "\U0001f3a1", "scratch": "\U0001f3ab", "coinchain": "\U0001fa99", "mines": "\U0001f4a3",
        "chicken_road": "\U0001f414",
    }
    emoji = emoji_map.get(game_key, "\U0001f3ae")
    await update.message.reply_text(
        f"\u2705 {emoji} <b>{game_key.title()}</b> game is now available.",
        parse_mode=ParseMode.HTML
    )

DASHBOARD_TEMPLATE_PATH = "clean_template.jpg"

def _resolve_dashboard_font():
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "bold.ttf",
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                return p
        except Exception:
            pass
    return "bold.ttf"

DASHBOARD_FONT_PATH = _resolve_dashboard_font()

DASHBOARD_FONT_FALLBACK = None  # Will use PIL default if custom font not found

DASHBOARD_CONFIG = {
    "profile_picture": {
        "position": (50, 60),      # (X, Y) position for profile picture - left side
        "size": (120, 120)         # Width and height
    },
    "name": {
        "position": (200, 70),     # (X, Y) position - User's first name
        "font_size": 32,           # Font size in pixels
        "color": (255, 255, 255)   # RGB color (white)
    },
    "username": {
        "position": (200, 110),    # Username (@username)
        "font_size": 20,
        "color": (180, 180, 180)   # Light gray
    },
    "user_id": {
        "position": (200, 145),    # User ID number
        "font_size": 16,
        "color": (200, 200, 200)   # Light gray
    },
    "level": {
        "position": (340, 145),    # Level badge - next to user ID
        "font_size": 16,
        "color": (150, 100, 200)   # Purple
    },
    "bot_username": {
        "position": (720, 35),     # Bot username in top right
        "font_size": 24,
        "color": (255, 215, 0)     # Gold
    },
    "member_since": {
        "position": (795, 85),     # Member since date - below bot username
        "font_size": 14,
        "color": (0, 255, 255)     # Cyan
    },
    "balance": {
        "position": (200, 300),    # Balance in left wide green box (60-470)
        "font_size": 28,
        "color": (0, 255, 0)       # Green
    },
    "last_win": {
        "position": (625, 300),    # Last win in right wide orange box (490-900)
        "font_size": 22,
        "color": (255, 255, 255)   # White
    }
}

SUPPORTED_FIATS = ["USD", "INR", "EUR", "GBP"]

SUPPORTED_DISPLAY_CURRENCIES = list(SUPPORTED_CRYPTOS) + SUPPORTED_FIATS

CURRENCY_RATES = {
    "USD": 1.0,
    "INR": 83.12,
    "EUR": 0.92,
    "GBP": 0.79,
}

LIVE_FIAT_RATES = dict(CURRENCY_RATES)  # USD -> fiat, refreshed on the fly

CURRENCY_SYMBOLS = {
    # Fiat
    "USD": "$",
    "INR": "\u20B9",   # ₹
    "EUR": "\u20AC",   # €
    "GBP": "\u00A3",   # £
    # Crypto (short visual tags used before the amount)
    "USDT": "\u20AE",  # ₮
    "BTC":  "\u20BF",  # ₿
    "ETH":  "\u039E",  # Ξ
    "SOL":  "\u25CE",  # ◎
    "BNB":  "\u25C6",  # ◆
    "TRX":  "\u25C8",  # ◈
    "LTC":  "\u0141",  # Ł
}

CURRENCY_EMOJI_KEY = {
    "USD":  "balance",
    "INR":  "money",
    "EUR":  "money",
    "GBP":  "money",
    "USDT": "usdt",
    "BTC":  "btc",
    "ETH":  "eth",
    "SOL":  "sol",
    "BNB":  "bnb",
    "TRX":  "trx",
    "LTC":  "ltc",
}

_INDIAN_SCALE_CURRENCIES = {"INR"}

def get_display_currency(user_id) -> str:
    """Return the user's preferred display currency.

    Falls back to their active crypto wallet (so existing users
    who never picked a display currency keep seeing amounts in
    their wallet coin instead of a sudden switch to USD)."""
    try:
        stats = user_stats.get(user_id, {}) or {}
        pref = stats.get("display_currency")
        if isinstance(pref, str) and pref.upper() in SUPPORTED_DISPLAY_CURRENCIES:
            return pref.upper()
    except Exception:
        pass
    try:
        active = get_active_currency(user_id)
        if active in SUPPORTED_DISPLAY_CURRENCIES:
            return active
    except Exception:
        pass
    return "USD"

def _rate_usd_to(currency: str) -> float:
    """1 USD -> N units of the given currency. Always > 0."""
    currency = (currency or "USD").upper()
    if currency == "USD":
        return 1.0
    if currency in SUPPORTED_CRYPTOS:
        price = float(LIVE_PRICES.get(currency, 0.0) or 0.0)
        # LIVE_PRICES stores coin->USD (i.e. 1 coin = price USD),
        # so 1 USD = 1/price of that coin.
        if price <= 0:
            return 0.0
        return 1.0 / price
    rate = float(LIVE_FIAT_RATES.get(currency, CURRENCY_RATES.get(currency, 0.0)) or 0.0)
    return rate if rate > 0 else 0.0

def convert_usd_to_display(amount_usd: float, currency: str) -> float:
    """Convert a USD amount into the given display currency."""
    rate = _rate_usd_to(currency)
    if rate <= 0:
        return 0.0
    return float(amount_usd) * rate

def convert_display_to_usd(amount: float, currency: str) -> float:
    """Convert a display-currency amount back to USD."""
    rate = _rate_usd_to(currency)
    if rate <= 0:
        return 0.0
    return float(amount) / rate

def _decimal_places(currency: str) -> int:
    c = (currency or "USD").upper()
    if c in SUPPORTED_FIATS:
        return 2
    return CRYPTO_PRECISION.get(c, 5) if "CRYPTO_PRECISION" in globals() else 5

def format_compact(amount: float, currency: str = "USD") -> str:
    """Compact large-number format, currency-aware.

    Indian-system (INR): K (thousand), L (lakh=1e5), Cr (crore=1e7).
    Short-scale (everything else): K, M (1e6), B (1e9), T (1e12).
    Small amounts fall back to the full decimal form with the right
    precision for the currency.
    """
    c = (currency or "USD").upper()
    sign = "-" if amount < 0 else ""
    a = abs(float(amount))
    if c in _INDIAN_SCALE_CURRENCIES:
        if a >= 1_00_00_000:       # >= 1 crore
            s = f"{a/1_00_00_000:.2f}Cr"
        elif a >= 1_00_000:        # >= 1 lakh
            s = f"{a/1_00_000:.2f}L"
        elif a >= 1_000:
            s = f"{a/1_000:.2f}K"
        else:
            s = f"{a:,.2f}"
    else:
        if a >= 1_000_000_000_000:
            s = f"{a/1_000_000_000_000:.2f}T"
        elif a >= 1_000_000_000:
            s = f"{a/1_000_000_000:.2f}B"
        elif a >= 1_000_000:
            s = f"{a/1_000_000:.2f}M"
        elif a >= 1_000:
            s = f"{a/1_000:.2f}K"
        else:
            dp = _decimal_places(c)
            s = f"{a:,.{min(dp,2)}f}" if c in SUPPORTED_FIATS else f"{a:,.2f}"
    # Trim pointless trailing zeros (e.g. 6.00L -> 6L, 6.30L -> 6.3L)
    if "." in s and any(ch.isalpha() for ch in s):
        head, tail = s.split(".", 1)
        letters = "".join(ch for ch in tail if ch.isalpha())
        digits  = "".join(ch for ch in tail if ch.isdigit())
        digits  = digits.rstrip("0")
        s = f"{head}.{digits}{letters}" if digits else f"{head}{letters}"
    return f"{sign}{s}"

def format_display_amount(
    amount_usd: float,
    currency: str = "USD",
    compact: bool = False,
    with_symbol: bool = True,
) -> str:
    """Render a USD-denominated amount in the chosen display currency.

    When ``compact`` is True uses format_compact (K/L/Cr/M/B/T).
    Otherwise uses full 2dp (fiat) or CRYPTO_PRECISION (crypto).
    """
    c = (currency or "USD").upper()
    disp = convert_usd_to_display(float(amount_usd or 0.0), c)
    sym = CURRENCY_SYMBOLS.get(c, "")
    if compact:
        body = format_compact(disp, c)
    else:
        if c in SUPPORTED_FIATS:
            body = f"{disp:,.2f}"
        else:
            dp = CRYPTO_PRECISION.get(c, 5)
            body = f"{disp:,.{dp}f}"
    if not with_symbol or not sym:
        return body
    if c in SUPPORTED_FIATS:
        return f"{sym}{body}"
    # Crypto: "0.012345 BTC" reads better than "₿0.012345"
    return f"{body} {c}"

def format_for_user(
    user_id,
    amount_usd: float,
    compact: bool = False,
    with_usdt_estimate: bool = False,
) -> str:
    """User-facing display helper.

    Used for every group/DM message that shows a balance, bet,
    win, or wager. When ``with_usdt_estimate`` is True and the
    user's display currency isn't USDT, appends
    ``(~ X.XX USDT)`` — exactly the format the group chats use.
    """
    cur = get_display_currency(user_id)
    head = format_display_amount(amount_usd, cur, compact=compact)
    if with_usdt_estimate and cur != "USDT":
        usdt_val = convert_usd_to_display(float(amount_usd or 0.0), "USDT")
        tail_body = format_compact(usdt_val, "USDT") if compact else f"{usdt_val:,.2f}"
        return f"{head} (~ {tail_body} USDT)"
    return head

def format_currency(amount_usd, currency="USD"):
    """Legacy helper - always returns the amount in the given currency.

    Kept USD-only-looking signature for backwards compat but now
    respects the currency argument. Most call sites pass a user's
    currency here already (e.g. get_user_currency(...))."""
    c = (currency or "USD").upper()
    if c not in SUPPORTED_DISPLAY_CURRENCIES:
        return f"${float(amount_usd or 0.0):,.2f}"
    return format_display_amount(amount_usd, c, compact=False, with_symbol=True)

async def update_live_fiat_rates():
    """Background task: refresh USD -> fiat rates every 30 min.

    Uses open.er-api.com (free, no key). Rates stay cached between
    refreshes; if the fetch fails we keep the last-known values so
    bets never see a zero rate.
    """
    global LIVE_FIAT_RATES
    while True:
        try:
            client = await _get_http_client()
            resp = await client.get(
                "https://open.er-api.com/v6/latest/USD", timeout=15.0
            )
            if resp.status_code == 200:
                payload = resp.json() or {}
                rates = payload.get("rates") or {}
                updated = {"USD": 1.0}
                for code in SUPPORTED_FIATS:
                    if code == "USD":
                        continue
                    val = rates.get(code)
                    if isinstance(val, (int, float)) and val > 0:
                        updated[code] = float(val)
                if len(updated) > 1:
                    LIVE_FIAT_RATES.update(updated)
                    CURRENCY_RATES.update(updated)
                    logging.info(
                        "Live FX rates updated: %s",
                        {k: f"{v:.4f}" for k, v in updated.items()},
                    )
            else:
                logging.warning("Fiat FX API returned status %s", resp.status_code)
        except Exception as e:
            logging.warning(f"Failed to fetch live fiat rates: {e}")
        await asyncio.sleep(30 * 60)  # 30 minutes

def parse_bet_amount(amount_str: str, user_id: int) -> tuple:
    """
    Parse a bet amount from user input.

    Interprets the number in the user's DISPLAY currency (so
    ``/bj 500`` with display_currency=INR means ₹500, not $500)
    and converts it to USD internally — the rest of the ledger
    stays USD-denominated.

    Returns ``(amount_in_usd, amount_in_display, display_currency)``.

    SECURITY: Rejects NaN/Inf/zero/negative/absurd values.
    """
    import math as _math_parse
    display_currency = get_display_currency(user_id)
    balance_usd = get_active_balance_usd(user_id)

    s = (amount_str or "").lower().strip()

    if s == "all":
        amount_usd = balance_usd
        amount_display = convert_usd_to_display(amount_usd, display_currency)
    elif s in ("half", "1/2"):
        amount_usd = balance_usd / 2
        amount_display = convert_usd_to_display(amount_usd, display_currency)
    else:
        try:
            amount_display = float(s)
        except ValueError:
            raise ValueError(f"Invalid bet amount: {amount_str!r}")
        amount_usd = convert_display_to_usd(amount_display, display_currency)

    if _math_parse.isnan(amount_usd) or _math_parse.isinf(amount_usd):
        raise ValueError("Invalid bet amount: NaN or Inf")
    if amount_usd <= 0:
        raise ValueError("Bet amount must be positive")
    if amount_usd > 1_000_000_000:  # $1B sanity cap
        raise ValueError("Bet amount exceeds maximum")

    amount_usd = round(amount_usd, 2)
    return amount_usd, amount_display, display_currency

def get_user_currency(user_id):
    """Legacy shim.

    Historically this returned the user's active crypto (which is what
    ``get_active_currency`` returns). Display call sites used that
    return value to format amounts, which broke as soon as we added
    a separate "display currency" concept. Every remaining caller of
    this function is a display call site, so we point it at the
    display currency. Wallet / ledger call sites have always used
    ``get_active_currency`` directly.
    """
    return get_display_currency(user_id)

ACHIEVEMENTS = {
    "wager_100": {"name": "🎲 Player", "description": "Wager a total of $100.", "emoji": "🎲", "type": "wager", "value": 100},
    "wager_1000": {"name": "💰 High Roller", "description": "Wager a total of $1,000.", "emoji": "💰", "type": "wager", "value": 1000},
    "wager_10000": {"name": "👑 Whale", "description": "Wager a total of $10,000.", "emoji": "👑", "type": "wager", "value": 10000},
    "wins_50": {"name": "👍 Winner", "description": "Win 50 games.", "emoji": "👍", "type": "wins", "value": 50},
    "wins_250": {"name": "🏆 Champion", "description": "Win 250 games.", "emoji": "🏆", "type": "wins", "value": 250},
    "pvp_wins_25": {"name": "⚔️ Duelist", "description": "Win 25 PvP matches.", "emoji": "⚔️", "type": "pvp_wins", "value": 25},
    "lucky_100x": {"name": "🌟 Lucky Star", "description": "Win a bet with a 100x or higher multiplier.", "emoji": "🌟", "type": "multiplier", "value": 100},
    "referral_master": {"name": "🤝 Connector", "description": "Refer 5 active users.", "emoji": "🤝", "type": "referrals", "value": 5},
}

LEVEL_ORDER = [
    "Bronze", "Silver", "Gold", "Platinum", "Diamond",
    "Emerald", "Ruby", "Sapphire"
]

LEVELS_DATA = {
    "Bronze": [
        ("Bronze I", 100, 1), ("Bronze II", 500, 2), ("Bronze III", 1000, 2.5),
        ("Bronze IV", 2500, 7.5), ("Bronze V", 5000, 12.5),
    ],
    "Silver": [
        ("Silver I", 10000, 25), ("Silver II", 15200, 26), ("Silver III", 20500, 26.5),
        ("Silver IV", 26000, 27.5), ("Silver V", 32000, 30),
    ],
    "Gold": [
        ("Gold I", 39000, 35), ("Gold II", 48000, 45), ("Gold III", 58000, 50),
        ("Gold IV", 69000, 55), ("Gold V", 81000, 60),
    ],
    "Platinum": [
        ("Platinum I", 94000, 65), ("Platinum II", 107500, 67.5), ("Platinum III", 122000, 72.5),
        ("Platinum IV", 138000, 80), ("Platinum V", 155000, 85),
    ],
    "Diamond": [
        ("Diamond I", 173000, 90), ("Diamond II", 192000, 95), ("Diamond III", 211500, 97.5),
        ("Diamond IV", 232000, 102), ("Diamond V", 253000, 105),
    ],
    "Emerald": [
        ("Emerald I", 275000, 110), ("Emerald II", 298000, 115), ("Emerald III", 322000, 120),
        ("Emerald IV", 347000, 125), ("Emerald V", 373000, 130),
    ],
    "Ruby": [
        ("Ruby I", 400000, 135), ("Ruby II", 428000, 140), ("Ruby III", 457000, 145),
        ("Ruby IV", 487000, 150), ("Ruby V", 518000, 155),
    ],
    "Sapphire": [
        ("Sapphire I", 550000, 160), ("Sapphire II", 583000, 165), ("Sapphire III", 617000, 170),
        ("Sapphire IV", 652000, 175), ("Sapphire V", 688000, 180),
    ]
}

TIER_RAKEBACK = {
    "Bronze": 1, "Silver": 3, "Gold": 5, "Platinum": 7,
    "Diamond": 9, "Emerald": 11, "Ruby": 13, "Sapphire": 15
}

TIER_EMOJI = {
    "Bronze": "🥉", "Silver": "🥈", "Gold": "🥇", "Platinum": "⭐",
    "Diamond": "💎", "Emerald": "🟢", "Ruby": "🔴", "Sapphire": "🔵"
}

LEVEL_NAVIGATION = {}

for i, tier in enumerate(LEVEL_ORDER):
    prev_t = LEVEL_ORDER[i-1] if i > 0 else None
    next_t = LEVEL_ORDER[i+1] if i < len(LEVEL_ORDER)-1 else None
    LEVEL_NAVIGATION[tier] = {"prev": prev_t, "next": next_t}

def _flatten_levels():
    """Return [(level_name, threshold_wager, bonus), ...] in progression order."""
    flat = []
    for tier in LEVEL_ORDER:
        for name, wager, bonus in LEVELS_DATA[tier]:
            flat.append((name, wager, bonus))
    return flat

ALL_LEVELS = _flatten_levels()

def get_user_lang(user_id):
    """Helper function to get user's language preference"""
    return user_stats.get(user_id, {}).get("userinfo", {}).get("language", DEFAULT_LANG)

LANGUAGE_FILES = {
    "en": "English.txt",
    "hi": "hindhi.txt",
    "es": "spanish.txt",
    "ru": "russian.txt",
    "fr": "french.txt",
    "zh": "chinese.txt"
}

LANGUAGE_NAMES = {
    "en": "English 🇬🇧",
    "hi": "हिन्दी 🇮🇳",
    "es": "Español 🇪🇸",
    "ru": "Русский 🇷🇺",
    "fr": "Français 🇫🇷",
    "zh": "中文 🇨🇳"
}

_language_cache = {}

def load_language_file(lang_code):
    """Load a language file and return as a dictionary"""
    if lang_code in _language_cache:
        return _language_cache[lang_code]

    filename = LANGUAGE_FILES.get(lang_code)
    if not filename:
        return None

    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        logging.warning(f"Language file not found: {filepath}")
        return None

    lang_dict = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            current_key = None
            current_value = []

            for line in f:
                line_rstrip = line.rstrip('\n')

                # Skip comments and empty lines when not in a multi-line value
                if not current_key and (not line_rstrip or line_rstrip.startswith('#')):
                    continue

                # Check for new key = "value" pattern
                if ' = "' in line_rstrip and not current_key:
                    parts = line_rstrip.split(' = "', 1)
                    if len(parts) == 2:
                        current_key = parts[0].strip()
                        value_part = parts[1]

                        # Check if value ends on this line
                        if value_part.endswith('"'):
                            lang_dict[current_key] = value_part[:-1]
                            current_key = None
                            current_value = []
                        else:
                            current_value = [value_part]
                elif current_key:
                    # Continuation of multi-line value
                    if line_rstrip.endswith('"'):
                        current_value.append(line_rstrip[:-1])
                        lang_dict[current_key] = '\n'.join(current_value)
                        current_key = None
                        current_value = []
                    else:
                        current_value.append(line_rstrip)

        _language_cache[lang_code] = lang_dict
        logging.info(f"Loaded language file: {filename} with {len(lang_dict)} entries")
        return lang_dict
    except Exception as e:
        logging.error(f"Error loading language file {filename}: {e}")
        return None

LANGUAGES = {
    "en": {  # English
        "language_name": "English 🇬🇧",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>Welcome to Telegram Casino & Escrow Bot!</b> 🎰",
        "hello": "👋 Hello {first_name}!",
        "welcome_desc": "🎲 Experience the thrill of casino games or secure your trades with our automated Escrow system.",
        "ai_feature": "✨ NEW: Chat with our <b>AI Assistant</b> for any questions or tasks!",
        "current_balance": "💰 Current Balance: <b>{balance}</b>",
        "choose_option": "Choose an option below to get started:",

        # Buttons
        "withdraw": "📤 Withdraw",
        "games": "🎮 Games",
        "more": "➕ More",
        "stats": "📊 Statistics",
        "settings": "⚙️ Settings",
        "help": "❓ Help",
        "bonuses": "🎁 Bonuses",
        "escrow": "🔐 Escrow",
        "ai_assistant": "🤖 AI Assistant",
        "back": "🔙 Back",
        "cancel": "❌ Cancel",
        "confirm": "✅ Confirm",

        # Balance and Currency
        "balance": "💰 Your balance: {balance}",
        "your_balance": "💰 Your balance: {balance}",
        "insufficient_balance": "❌ Insufficient balance. Please deposit to continue.",
        "locked_in_games": "+ {amount} locked in games",

        # Betting
        "enter_bet_amount": "Enter your bet amount:",
        "bet_placed": "🎲 Bet placed: ${amount:.2f}",
        "invalid_amount": "Invalid amount. Please enter a valid number or 'all'.",
        "min_bet": "Minimum bet for this game is {amount}",
        "max_bet": "Maximum bet for this game is {amount}",

        # Game Results
        "you_won": "🎉 You won {amount}!",
        "you_lost": "😔 You lost. Better luck next time!",
        "game_started": "🎮 Game started!",
        "game_ended": "🎮 Game ended!",
        "round": "Round {round}",
        "waiting_for_opponent": "⏳ Waiting for opponent...",

        # Daily Bonus
        "daily_claim_success": "🎉 You have successfully claimed your daily bonus of {amount}!",
        "daily_claim_wait": "⏳ You have already claimed your daily bonus. Please wait {hours}h {minutes}m before claiming again.",
        "daily_bonus": "🎁 Daily Bonus",

        # Achievements
        "achievement_unlocked": "🏅 <b>Achievement Unlocked!</b> 🏅\n\nYou have earned the <b>{emoji} {name}</b> badge!\n<i>{description}</i>",
        "achievements": "🏅 Achievements",
        "no_achievements": "You haven't unlocked any achievements yet. Start playing to earn badges!",

        # Language
        "language_set": "✅ Language set to English",
        "select_language": "🌍 <b>Select your language:</b>",
        "language": "Language",

        # Games Menu
        "games_menu": "🎮 <b>Casino Games</b>\n\nChoose a category:",
        "dice_games": "🎲 Dice Games",
        "card_games": "🃏 Card Games",
        "original_games": "⭐ Original Games",
        "quick_games": "⚡ Quick Games",

        # Settings
        "settings_menu": "⚙️ <b>Settings</b>\n\nCustomize your experience:",
        "withdrawal_address": "Withdrawal Address",
        "currency_settings": "💱 Currency",
        "recovery_settings": "🔐 Recovery",

        # Help
        "help_text": "❓ <b>Help & Commands</b>\n\nAvailable commands:\n/start - Main menu\n/games - Browse games\n/balance - Check balance\n/withdraw - Withdraw funds\n/stats - View statistics\n/daily - Claim daily bonus\n/help - Show this help\n\nFor support, contact @jashanxjagy",

        # Errors
        "error_occurred": "❌ An error occurred. Please try again.",
        "command_not_found": "❌ Command not found. Use /help to see available commands.",
        "maintenance_mode": "🛠️ <b>Bot Under Maintenance</b> 🛠️\n\nThe bot is currently undergoing scheduled maintenance.",
        "banned_user": "You have been banned from using this bot.",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>Withdraw</b>\n\nEnter the amount you want to withdraw:",
        "withdrawal_success": "✅ Withdrawal request submitted successfully!",
        "withdrawal_pending": "Your withdrawal is being processed...",

        # Admin
        "admin_panel": "👑 <b>Admin Panel</b>",
        "admin_only": "This command is only available to administrators.",

        # Misc
        "coming_soon": "🚧 Coming Soon!",
        "feature_disabled": "This feature is currently disabled.",
        "loading": "⏳ Loading...",
        "processing": "⏳ Processing...",

        # Game-specific messages
        "dice_game": "🎲 Dice",
        "darts_game": "🎯 Darts",
        "football_game": "⚽ Football",
        "bowling_game": "🎳 Bowling",
        "blackjack_game": "🃏 Blackjack",
        "roulette_game": "🎯 Roulette",
        "slots_game": "🎰 Slots",
        "play_vs_bot": "🤖 Play vs Bot",
        "play_vs_player": "👤 Play vs Player",
        "who_to_play": "Who do you want to play against?",
        "bot_rolling": "Bot is rolling...",
        "your_turn": "Your turn! Send {rolls} {emoji}!",
        "bot_rolled": "Bot rolled: {rolls_text} = <b>{total}</b>",
        "you_rolled": "You rolled: {rolls_text} = <b>{total}</b>",
        "you_win_round": "You win this round!",
        "bot_wins_round": "Bot wins this round!",
        "tie_round": "It's a tie! No point.",
        "you_win_game": "🏆 Congratulations! You beat the bot ({user_score}-{bot_score}) and win {amount}!",
        "bot_wins_game": "😔 Bot wins the match ({bot_score}-{user_score}). You lost {amount}.",
        "score_update": "Score: You {user_score} - {bot_score} Bot. (First to {target})",
        "roll_complete": "Roll {current}/{total} complete. Send {remaining} more {emoji}!",
        "normal_mode": "🎮 Normal Mode",
        "crazy_mode": "🔥 Crazy Mode",
        "select_mode": "Select game mode:",
        "select_rolls": "Select number of rolls:",
        "select_target": "Select target score:",
        "game_created": "🎯 Game created! Waiting for opponent...",
        "usage_dice": "Usage: /dice <amount>\nExample: /dice 5 or /dice all",
        "usage_darts": "Usage: /darts <amount>\nExample: /darts 5 or /darts all",
        "usage_goal": "Usage: /goal <amount>\nExample: /goal 5 or /goal all",
        "usage_bowl": "Usage: /bowl <amount>\nExample: /bowl 5 or /bowl all",
    },
    "es": {  # Spanish
        "language_name": "Español 🇪🇸",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>¡Bienvenido al Bot de Casino y Escrow de Telegram!</b> 🎰",
        "hello": "👋 ¡Hola {first_name}!",
        "welcome_desc": "🎲 Experimenta la emoción de los juegos de casino o asegura tus operaciones con nuestro sistema automatizado de Escrow.",
        "ai_feature": "✨ NUEVO: ¡Chatea con nuestro <b>Asistente IA</b> para cualquier pregunta o tarea!",
        "current_balance": "💰 Saldo Actual: <b>{balance}</b>",
        "choose_option": "Elige una opción para comenzar:",

        # Buttons
        "withdraw": "📤 Retirar",
        "games": "🎮 Juegos",
        "more": "➕ Más",
        "stats": "📊 Estadísticas",
        "settings": "⚙️ Configuración",
        "help": "❓ Ayuda",
        "bonuses": "🎁 Bonos",
        "escrow": "🔐 Depósito en garantía",
        "ai_assistant": "🤖 Asistente IA",
        "back": "🔙 Atrás",
        "cancel": "❌ Cancelar",
        "confirm": "✅ Confirmar",

        # Balance and Currency
        "balance": "💰 Tu saldo: {balance}",
        "your_balance": "💰 Tu saldo: {balance}",
        "insufficient_balance": "❌ Saldo insuficiente. Por favor deposita para continuar.",
        "locked_in_games": "+ {amount} bloqueado en juegos",

        # Betting
        "enter_bet_amount": "Ingresa tu cantidad de apuesta:",
        "bet_placed": "🎲 Apuesta realizada: ${amount:.2f}",
        "invalid_amount": "Cantidad inválida. Por favor ingresa un número válido o 'all'.",
        "min_bet": "La apuesta mínima para este juego es {amount}",
        "max_bet": "La apuesta máxima para este juego es {amount}",

        # Game Results
        "you_won": "🎉 ¡Ganaste {amount}!",
        "you_lost": "😔 Perdiste. ¡Mejor suerte la próxima vez!",
        "game_started": "🎮 ¡Juego iniciado!",
        "game_ended": "🎮 ¡Juego terminado!",
        "round": "Ronda {round}",
        "waiting_for_opponent": "⏳ Esperando oponente...",

        # Daily Bonus
        "daily_claim_success": "🎉 ¡Has reclamado con éxito tu bono diario de {amount}!",
        "daily_claim_wait": "⏳ Ya has reclamado tu bono diario. Por favor, espera {hours}h {minutes}m antes de volver a reclamar.",
        "daily_bonus": "🎁 Bono Diario",

        # Achievements
        "achievement_unlocked": "🏅 <b>¡Logro Desbloqueado!</b> 🏅\n\n¡Has ganado la insignia <b>{emoji} {name}</b>!\n<i>{description}</i>",
        "achievements": "🏅 Logros",
        "no_achievements": "Aún no has desbloqueado ningún logro. ¡Comienza a jugar para ganar insignias!",

        # Language
        "language_set": "✅ Idioma configurado a Español",
        "select_language": "🌍 <b>Selecciona tu idioma:</b>",
        "language": "Idioma",

        # Games Menu
        "games_menu": "🎮 <b>Juegos de Casino</b>\n\nElige una categoría:",
        "dice_games": "🎲 Juegos de Dados",
        "card_games": "🃏 Juegos de Cartas",
        "original_games": "⭐ Juegos Originales",
        "quick_games": "⚡ Juegos Rápidos",

        # Settings
        "settings_menu": "⚙️ <b>Configuración</b>\n\nPersonaliza tu experiencia:",
        "withdrawal_address": "Dirección de Retiro",
        "currency_settings": "💱 Moneda",
        "recovery_settings": "🔐 Recuperación",

        # Help
        "help_text": "❓ <b>Ayuda y Comandos</b>\n\nComandos disponibles:\n/start - Menú principal\n/games - Ver juegos\n/balance - Ver saldo\n/withdraw - Retirar fondos\n/stats - Ver estadísticas\n/daily - Reclamar bono diario\n/help - Mostrar esta ayuda\n\nPara soporte, contacta @jashanxjagy",

        # Errors
        "error_occurred": "❌ Ocurrió un error. Por favor intenta de nuevo.",
        "command_not_found": "❌ Comando no encontrado. Usa /help para ver los comandos disponibles.",
        "maintenance_mode": "🛠️ <b>Bot en Mantenimiento</b> 🛠️\n\nEl bot está actualmente en mantenimiento programado.",
        "banned_user": "Has sido bloqueado del uso de este bot.",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>Retirar</b>\n\nIngresa la cantidad que deseas retirar:",
        "withdrawal_success": "✅ ¡Solicitud de retiro enviada exitosamente!",
        "withdrawal_pending": "Tu retiro está siendo procesado...",

        # Admin
        "admin_panel": "👑 <b>Panel de Administración</b>",
        "admin_only": "Este comando solo está disponible para administradores.",

        # Misc
        "coming_soon": "🚧 ¡Próximamente!",
        "feature_disabled": "Esta característica está actualmente deshabilitada.",
        "loading": "⏳ Cargando...",
        "processing": "⏳ Procesando...",

        # Game-specific messages
        "dice_game": "🎲 Dados",
        "darts_game": "🎯 Dardos",
        "football_game": "⚽ Fútbol",
        "bowling_game": "🎳 Bolos",
        "blackjack_game": "🃏 Blackjack",
        "roulette_game": "🎯 Ruleta",
        "slots_game": "🎰 Tragamonedas",
        "play_vs_bot": "🤖 Jugar vs Bot",
        "play_vs_player": "👤 Jugar vs Jugador",
        "who_to_play": "¿Contra quién quieres jugar?",
        "bot_rolling": "El bot está tirando...",
        "your_turn": "¡Tu turno! ¡Envía {rolls} {emoji}!",
        "bot_rolled": "Bot tiró: {rolls_text} = <b>{total}</b>",
        "you_rolled": "Tiraste: {rolls_text} = <b>{total}</b>",
        "you_win_round": "¡Ganas esta ronda!",
        "bot_wins_round": "¡El bot gana esta ronda!",
        "tie_round": "¡Es un empate! Sin punto.",
        "you_win_game": "🏆 ¡Felicidades! Venciste al bot ({user_score}-{bot_score}) y ganas {amount}!",
        "bot_wins_game": "😔 El bot gana el partido ({bot_score}-{user_score}). Perdiste {amount}.",
        "score_update": "Puntuación: Tú {user_score} - {bot_score} Bot. (Primero a {target})",
        "roll_complete": "Tirada {current}/{total} completa. ¡Envía {remaining} más {emoji}!",
        "normal_mode": "🎮 Modo Normal",
        "crazy_mode": "🔥 Modo Loco",
        "select_mode": "Selecciona el modo de juego:",
        "select_rolls": "Selecciona el número de tiradas:",
        "select_target": "Selecciona puntuación objetivo:",
        "game_created": "🎯 ¡Juego creado! Esperando oponente...",
        "usage_dice": "Uso: /dice <cantidad>\nEjemplo: /dice 5 o /dice all",
        "usage_darts": "Uso: /darts <cantidad>\nEjemplo: /darts 5 o /darts all",
        "usage_goal": "Uso: /goal <cantidad>\nEjemplo: /goal 5 o /goal all",
        "usage_bowl": "Uso: /bowl <cantidad>\nEjemplo: /bowl 5 o /bowl all",
    },
    "fr": {  # French
        "language_name": "Français 🇫🇷",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>Bienvenue au Bot de Casino et Escrow Telegram!</b> 🎰",
        "hello": "👋 Bonjour {first_name}!",
        "welcome_desc": "🎲 Vivez l'excitation des jeux de casino ou sécurisez vos transactions avec notre système Escrow automatisé.",
        "ai_feature": "✨ NOUVEAU: Chattez avec notre <b>Assistant IA</b> pour toute question ou tâche!",
        "current_balance": "💰 Solde Actuel: <b>{balance}</b>",
        "choose_option": "Choisissez une option ci-dessous pour commencer:",

        # Buttons
        "withdraw": "📤 Retrait",
        "games": "🎮 Jeux",
        "more": "➕ Plus",
        "stats": "📊 Statistiques",
        "settings": "⚙️ Paramètres",
        "help": "❓ Aide",
        "bonuses": "🎁 Bonus",
        "escrow": "🔐 Dépôt fiduciaire",
        "ai_assistant": "🤖 Assistant IA",
        "back": "🔙 Retour",
        "cancel": "❌ Annuler",
        "confirm": "✅ Confirmer",

        # Balance and Currency
        "balance": "💰 Votre solde: {balance}",
        "your_balance": "💰 Votre solde: {balance}",
        "insufficient_balance": "❌ Solde insuffisant. Veuillez déposer pour continuer.",
        "locked_in_games": "+ {amount} bloqué dans les jeux",

        # Betting
        "enter_bet_amount": "Entrez votre montant de pari:",
        "bet_placed": "🎲 Pari placé: ${amount:.2f}",
        "invalid_amount": "Montant invalide. Veuillez entrer un nombre valide ou 'all'.",
        "min_bet": "La mise minimale pour ce jeu est {amount}",
        "max_bet": "La mise maximale pour ce jeu est {amount}",

        # Game Results
        "you_won": "🎉 Vous avez gagné {amount}!",
        "you_lost": "😔 Vous avez perdu. Meilleure chance la prochaine fois!",
        "game_started": "🎮 Jeu commencé!",
        "game_ended": "🎮 Jeu terminé!",
        "round": "Tour {round}",
        "waiting_for_opponent": "⏳ En attente de l'adversaire...",

        # Daily Bonus
        "daily_claim_success": "🎉 Vous avez réclamé avec succès votre bonus quotidien de {amount}!",
        "daily_claim_wait": "⏳ Vous avez déjà réclamé votre bonus quotidien. Veuillez attendre {hours}h {minutes}m avant de réclamer à nouveau.",
        "daily_bonus": "🎁 Bonus Quotidien",

        # Achievements
        "achievement_unlocked": "🏅 <b>Succès Débloqué!</b> 🏅\n\nVous avez gagné le badge <b>{emoji} {name}</b>!\n<i>{description}</i>",
        "achievements": "🏅 Succès",
        "no_achievements": "Vous n'avez pas encore débloqué de succès. Commencez à jouer pour gagner des badges!",

        # Language
        "language_set": "✅ Langue définie sur Français",
        "select_language": "🌍 <b>Sélectionnez votre langue:</b>",
        "language": "Langue",

        # Games Menu
        "games_menu": "🎮 <b>Jeux de Casino</b>\n\nChoisissez une catégorie:",
        "dice_games": "🎲 Jeux de Dés",
        "card_games": "🃏 Jeux de Cartes",
        "original_games": "⭐ Jeux Originaux",
        "quick_games": "⚡ Jeux Rapides",

        # Settings
        "settings_menu": "⚙️ <b>Paramètres</b>\n\nPersonnalisez votre expérience:",
        "withdrawal_address": "Adresse de Retrait",
        "currency_settings": "💱 Devise",
        "recovery_settings": "🔐 Récupération",

        # Help
        "help_text": "❓ <b>Aide et Commandes</b>\n\nCommandes disponibles:\n/start - Menu principal\n/games - Parcourir les jeux\n/balance - Vérifier le solde\n/withdraw - Retirer des fonds\n/stats - Voir les statistiques\n/daily - Réclamer le bonus quotidien\n/help - Afficher cette aide\n\nPour le support, contactez @jashanxjagy",

        # Errors
        "error_occurred": "❌ Une erreur s'est produite. Veuillez réessayer.",
        "command_not_found": "❌ Commande non trouvée. Utilisez /help pour voir les commandes disponibles.",
        "maintenance_mode": "🛠️ <b>Bot en Maintenance</b> 🛠️\n\nLe bot est actuellement en maintenance programmée.",
        "banned_user": "Vous avez été banni de l'utilisation de ce bot.",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>Retrait</b>\n\nEntrez le montant que vous souhaitez retirer:",
        "withdrawal_success": "✅ Demande de retrait soumise avec succès!",
        "withdrawal_pending": "Votre retrait est en cours de traitement...",

        # Admin
        "admin_panel": "👑 <b>Panneau d'Administration</b>",
        "admin_only": "Cette commande n'est disponible que pour les administrateurs.",

        # Misc
        "coming_soon": "🚧 Bientôt disponible!",
        "feature_disabled": "Cette fonctionnalité est actuellement désactivée.",
        "loading": "⏳ Chargement...",
        "processing": "⏳ Traitement...",

        # Game-specific messages
        "dice_game": "🎲 Dés",
        "darts_game": "🎯 Fléchettes",
        "football_game": "⚽ Football",
        "bowling_game": "🎳 Bowling",
        "blackjack_game": "🃏 Blackjack",
        "roulette_game": "🎯 Roulette",
        "slots_game": "🎰 Machines à sous",
        "play_vs_bot": "🤖 Jouer vs Bot",
        "play_vs_player": "?? Jouer vs Joueur",
        "who_to_play": "Contre qui voulez-vous jouer?",
        "bot_rolling": "Le bot lance...",
        "your_turn": "Votre tour! Envoyez {rolls} {emoji}!",
        "bot_rolled": "Bot a lancé: {rolls_text} = <b>{total}</b>",
        "you_rolled": "Vous avez lancé: {rolls_text} = <b>{total}</b>",
        "you_win_round": "Vous gagnez ce tour!",
        "bot_wins_round": "Le bot gagne ce tour!",
        "tie_round": "C'est une égalité! Aucun point.",
        "you_win_game": "🏆 Félicitations! Vous avez battu le bot ({user_score}-{bot_score}) et gagnez {amount}!",
        "bot_wins_game": "😔 Le bot gagne le match ({bot_score}-{user_score}). Vous avez perdu {amount}.",
        "score_update": "Score: Vous {user_score} - {bot_score} Bot. (Premier à {target})",
        "roll_complete": "Lancer {current}/{total} terminé. Envoyez {remaining} de plus {emoji}!",
        "normal_mode": "🎮 Mode Normal",
        "crazy_mode": "🔥 Mode Fou",
        "select_mode": "Sélectionnez le mode de jeu:",
        "select_rolls": "Sélectionnez le nombre de lancers:",
        "select_target": "Sélectionnez le score cible:",
        "game_created": "🎯 Jeu créé! En attente d'adversaire...",
        "usage_dice": "Utilisation: /dice <montant>\nExemple: /dice 5 ou /dice all",
        "usage_darts": "Utilisation: /darts <montant>\nExemple: /darts 5 ou /darts all",
        "usage_goal": "Utilisation: /goal <montant>\nExemple: /goal 5 ou /goal all",
        "usage_bowl": "Utilisation: /bowl <montant>\nExemple: /bowl 5 ou /bowl all",
    },
    "ru": {  # Russian
        "language_name": "Русский 🇷🇺",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>Добро пожаловать в Telegram Casino & Escrow Bot!</b> 🎰",
        "hello": "👋 Здравствуйте, {first_name}!",
        "welcome_desc": "🎲 Испытайте острые ощущения от азартных игр или обезопасьте свои сделки с помощью нашей автоматизированной системы Escrow.",
        "ai_feature": "✨ НОВИНКА: Общайтесь с нашим <b>ИИ Помощником</b> для любых вопросов или задач!",
        "current_balance": "💰 Текущий Баланс: <b>{balance}</b>",
        "choose_option": "Выберите опцию ниже, чтобы начать:",

        # Buttons
        "withdraw": "📤 Вывести",
        "games": "🎮 Игры",
        "more": "➕ Ещё",
        "stats": "📊 Статистика",
        "settings": "⚙️ Настройки",
        "help": "❓ Помощь",
        "bonuses": "🎁 Бонусы",
        "escrow": "🔐 Эскроу",
        "ai_assistant": "🤖 ИИ Помощник",
        "back": "🔙 Назад",
        "cancel": "❌ Отмена",
        "confirm": "✅ Подтвердить",

        # Balance and Currency
        "balance": "💰 Ваш баланс: {balance}",
        "your_balance": "💰 Ваш баланс: {balance}",
        "insufficient_balance": "❌ Недостаточно средств. Пожалуйста, пополните счет.",
        "locked_in_games": "+ {amount} заблокировано в играх",

        # Betting
        "enter_bet_amount": "Введите сумму ставки:",
        "bet_placed": "🎲 Ставка сделана: ${amount:.2f}",
        "invalid_amount": "Неверная сумма. Пожалуйста, введите правильное число или 'all'.",
        "min_bet": "Минимальная ставка для этой игры {amount}",
        "max_bet": "Максимальная ставка для этой игры {amount}",

        # Game Results
        "you_won": "🎉 Вы выиграли {amount}!",
        "you_lost": "😔 Вы проиграли. Удачи в следующий раз!",
        "game_started": "🎮 Игра началась!",
        "game_ended": "🎮 Игра закончилась!",
        "round": "Раунд {round}",
        "waiting_for_opponent": "⏳ Ожидание противника...",

        # Daily Bonus
        "daily_claim_success": "🎉 Вы успешно получили ежедневный бонус {amount}!",
        "daily_claim_wait": "⏳ Вы уже получили свой ежедневный бонус. Подождите {hours}ч {minutes}м перед следующим получением.",
        "daily_bonus": "🎁 Ежедневный Бонус",

        # Achievements
        "achievement_unlocked": "🏅 <b>Достижение Разблокировано!</b> 🏅\n\nВы получили значок <b>{emoji} {name}</b>!\n<i>{description}</i>",
        "achievements": "🏅 Достижения",
        "no_achievements": "Вы еще не разблокировали никаких достижений. Начните играть, чтобы заработать значки!",

        # Language
        "language_set": "✅ Язык установлен на Русский",
        "select_language": "🌍 <b>Выберите ваш язык:</b>",
        "language": "🌍 Язык",

        # Games Menu
        "games_menu": "🎮 <b>Игры Казино</b>\n\nВыберите категорию:",
        "dice_games": "🎲 Игры в Кости",
        "card_games": "🃏 Карточные Игры",
        "original_games": "⭐ Оригинальные Игры",
        "quick_games": "⚡ Быстрые Игры",

        # Settings
        "settings_menu": "⚙️ <b>Настройки</b>\n\nНастройте свой опыт:",
        "withdrawal_address": "💳 Адрес для Вывода",
        "currency_settings": "💱 Валюта",
        "recovery_settings": "🔐 Восстановление",

        # Help
        "help_text": "❓ <b>Помощь и Команды</b>\n\nДоступные команды:\n/start - Главное меню\n/games - Просмотр игр\n/balance - Проверить баланс\n/withdraw - Вывести средства\n/stats - Просмотр статистики\n/daily - Получить ежедневный бонус\n/help - Показать эту помощь\n\nДля поддержки, свяжитесь @jashanxjagy",

        # Errors
        "error_occurred": "❌ Произошла ошибка. Пожалуйста, попробуйте снова.",
        "command_not_found": "❌ Команда не найдена. Используйте /help, чтобы увидеть доступные команды.",
        "maintenance_mode": "🛠️ <b>Бот на Обслуживании</b> 🛠️\n\nБот в настоящее время находится на плановом обслуживании.",
        "banned_user": "Вы заблокированы от использования этого бота.",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>Вывод</b>\n\nВведите сумму, которую хотите вывести:",
        "withdrawal_success": "✅ Запрос на вывод успешно отправлен!",
        "withdrawal_pending": "Ваш вывод обрабатывается...",

        # Admin
        "admin_panel": "👑 <b>Панель Администратора</b>",
        "admin_only": "Эта команда доступна только администраторам.",

        # Misc
        "coming_soon": "🚧 Скоро!",
        "feature_disabled": "Эта функция в настоящее время отключена.",
        "loading": "⏳ Загрузка...",
        "processing": "⏳ Обработка...",

        # Game-specific messages
        "dice_game": "🎲 Кости",
        "darts_game": "🎯 Дартс",
        "football_game": "⚽ Футбол",
        "bowling_game": "🎳 Боулинг",
        "blackjack_game": "🃏 Блэкджек",
        "roulette_game": "🎯 Рулетка",
        "slots_game": "🎰 Слоты",
        "play_vs_bot": "🤖 Играть с Ботом",
        "play_vs_player": "👤 Играть с Игроком",
        "who_to_play": "С кем хотите играть?",
        "bot_rolling": "Бот бросает...",
        "your_turn": "Ваш ход! Отправьте {rolls} {emoji}!",
        "bot_rolled": "Бот бросил: {rolls_text} = <b>{total}</b>",
        "you_rolled": "Вы бросили: {rolls_text} = <b>{total}</b>",
        "you_win_round": "Вы выиграли этот раунд!",
        "bot_wins_round": "Бот выиграл этот раунд!",
        "tie_round": "Ничья! Без очка.",
        "you_win_game": "🏆 Поздравляем! Вы победили бота ({user_score}-{bot_score}) и выиграли {amount}!",
        "bot_wins_game": "😔 Бот выиграл матч ({bot_score}-{user_score}). Вы проиграли {amount}.",
        "score_update": "Счёт: Вы {user_score} - {bot_score} Бот. (Первый до {target})",
        "roll_complete": "Бросок {current}/{total} завершён. Отправьте ещё {remaining} {emoji}!",
        "normal_mode": "🎮 Обычный Режим",
        "crazy_mode": "🔥 Сумасшедший Режим",
        "select_mode": "Выберите режим игры:",
        "select_rolls": "Выберите количество бросков:",
        "select_target": "Выберите целевой счёт:",
        "game_created": "🎯 Игра создана! Ожидание противника...",
        "usage_dice": "Использование: /dice <сумма>\nПример: /dice 5 или /dice all",
        "usage_darts": "Использование: /darts <сумма>\nПример: /darts 5 или /darts all",
        "usage_goal": "Использование: /goal <сумма>\nПример: /goal 5 или /goal all",
        "usage_bowl": "Использование: /bowl <сумма>\nПример: /bowl 5 или /bowl all",
    },
    "hi": {  # Hindi
        "language_name": "हिन्दी 🇮🇳",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>टेलीग्राम कैसीनो और एस्क्रो बॉट में आपका स्वागत है!</b> 🎰",
        "hello": "👋 नमस्ते {first_name}!",
        "welcome_desc": "🎲 कैसीनो खेलों के रोमांच का अनुभव करें या हमारे स्वचालित एस्क्रो सिस्टम के साथ अपने लेन-देन को सुरक्षित रखें।",
        "ai_feature": "✨ नया: किसी भी प्रश्न या कार्य के लिए हमारे <b>एआई सहायक</b> से चैट करें!",
        "current_balance": "💰 वर्तमान शेष: <b>{balance}</b>",
        "choose_option": "शुरू करने के लिए नीचे एक विकल्प चुनें:",

        # Buttons
        "withdraw": "📤 निकालें",
        "games": "🎮 खेल",
        "more": "➕ और",
        "stats": "📊 आंकड़े",
        "settings": "⚙️ सेटिंग्स",
        "help": "❓ मदद",
        "bonuses": "🎁 बोनस",
        "escrow": "🔐 एस्क्रो",
        "ai_assistant": "🤖 एआई सहायक",
        "back": "🔙 वापस",
        "cancel": "❌ रद्द करें",
        "confirm": "✅ पुष्टि करें",

        # Balance and Currency
        "balance": "💰 आपका शेष: {balance}",
        "your_balance": "💰 आपका शेष: {balance}",
        "insufficient_balance": "❌ अपर्याप्त शेष राशि। कृपया जारी रखने के लिए जमा करें।",
        "locked_in_games": "+ {amount} खेलों में लॉक",

        # Betting
        "enter_bet_amount": "अपनी दांव राशि दर्ज करें:",
        "bet_placed": "🎲 दांव लगाया गया: ${amount:.2f}",
        "invalid_amount": "अमान्य राशि। कृपया एक वैध संख्या या 'all' दर्ज करें।",
        "min_bet": "इस खेल के लिए न्यूनतम दांव {amount} है",
        "max_bet": "इस खेल के लिए अधिकतम दांव {amount} है",

        # Game Results
        "you_won": "🎉 आपने {amount} जीता!",
        "you_lost": "😔 आप हार गए। अगली बार के लिए शुभकामनाएं!",
        "game_started": "🎮 खेल शुरू हुआ!",
        "game_ended": "🎮 खेल समाप्त हुआ!",
        "round": "राउंड {round}",
        "waiting_for_opponent": "⏳ प्रतिद्वंद्वी की प्रतीक्षा में...",

        # Daily Bonus
        "daily_claim_success": "🎉 आपने सफलतापूर्वक {amount} का दैनिक बोनस प्राप्त किया!",
        "daily_claim_wait": "⏳ आपने पहले ही अपना दैनिक बोनस प्राप्त कर लिया है। कृपया {hours}घं {minutes}मि प्रतीक्षा करें।",
        "daily_bonus": "🎁 दैनिक बोनस",

        # Achievements
        "achievement_unlocked": "🏅 <b>उपलब्धि अनलॉक!</b> 🏅\n\nआपने <b>{emoji} {name}</b> बैज अर्जित किया!\n<i>{description}</i>",
        "achievements": "🏅 उपलब्धियां",
        "no_achievements": "आपने अभी तक कोई उपलब्धि अनलॉक नहीं की है। बैज अर्जित करने के लिए खेलना शुरू करें!",

        # Language
        "language_set": "✅ भाषा हिन्दी पर सेट की गई",
        "select_language": "🌍 <b>अपनी भाषा चुनें:</b>",
        "language": "भाषा",

        # Games Menu
        "games_menu": "🎮 <b>कैसीनो खेल</b>\n\nएक श्रेणी चुनें:",
        "dice_games": "🎲 पासा खेल",
        "card_games": "🃏 ताश के खेल",
        "original_games": "⭐ मूल खेल",
        "quick_games": "⚡ त्वरित खेल",

        # Settings
        "settings_menu": "⚙️ <b>सेटिंग्स</b>\n\nअपने अनुभव को अनुकूलित करें:",
        "withdrawal_address": "निकासी पता",
        "currency_settings": "💱 मुद्रा",
        "recovery_settings": "🔐 पुनर्प्राप्ति",

        # Help
        "help_text": "❓ <b>सहायता और आदेश</b>\n\nउपलब्ध आदेश:\n/start - मुख्य मेनू\n/games - खेल ब्राउज़ करें\n/balance - शेष जांचें\n/withdraw - निकालें\n/stats - आंकड़े देखें\n/daily - दैनिक बोनस प्राप्त करें\n/help - यह सहायता दिखाएं\n\nसहायता के लिए, @jashanxjagy से संपर्क करें",

        # Errors
        "error_occurred": "❌ एक त्रुटि हुई। कृपया पुन: प्रयास करें।",
        "command_not_found": "❌ आदेश नहीं मिला। उपलब्ध आदेश देखने के लिए /help का उपयोग करें।",
        "maintenance_mode": "🛠️ <b>बॉट रखरखाव में</b> 🛠️\n\nबॉट वर्तमान में निर्धारित रखरखाव में है।",
        "banned_user": "आपको इस बॉट का उपयोग करने से प्रतिबंधित कर दिया गया है।",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>निकासी</b>\n\nवह राशि दर्ज करें जो आप निकालना चाहते हैं:",
        "withdrawal_success": "✅ निकासी अनुरोध सफलतापूर्वक सबमिट किया गया!",
        "withdrawal_pending": "आपकी निकासी प्रक्रिया में है...",

        # Admin
        "admin_panel": "👑 <b>व्यवस्थापक पैनल</b>",
        "admin_only": "यह आदेश केवल व्यवस्थापकों के लिए उपलब्ध है।",

        # Misc
        "coming_soon": "🚧 जल्द आ रहा है!",
        "feature_disabled": "यह सुविधा वर्तमान में अक्षम है।",
        "loading": "⏳ लोड हो रहा है...",
        "processing": "⏳ प्रक्रिया में...",

        # Game-specific messages
        "dice_game": "🎲 पासा",
        "darts_game": "🎯 डार्ट्स",
        "football_game": "⚽ फुटबॉल",
        "bowling_game": "🎳 बॉलिंग",
        "blackjack_game": "🃏 ब्लैकजैक",
        "roulette_game": "🎯 रूले",
        "slots_game": "🎰 स्लॉट्स",
        "play_vs_bot": "🤖 बॉट के खिलाफ खेलें",
        "play_vs_player": "👤 खिलाड़ी के खिलाफ खेलें",
        "who_to_play": "आप किसके खिलाफ खेलना चाहते हैं?",
        "bot_rolling": "बॉट रोल कर रहा है...",
        "your_turn": "आपकी बारी! {rolls} {emoji} भेजें!",
        "bot_rolled": "बॉट ने रोल किया: {rolls_text} = <b>{total}</b>",
        "you_rolled": "आपने रोल किया: {rolls_text} = <b>{total}</b>",
        "you_win_round": "आप यह राउंड जीत गए!",
        "bot_wins_round": "बॉट यह राउंड जीत गया!",
        "tie_round": "यह बराबरी है! कोई अंक नहीं।",
        "you_win_game": "🏆 बधाई हो! आपने बॉट को हराया ({user_score}-{bot_score}) और {amount} जीता!",
        "bot_wins_game": "😔 बॉट मैच जीत गया ({bot_score}-{user_score})। आपने {amount} खो दिया।",
        "score_update": "स्कोर: आप {user_score} - {bot_score} बॉट। (पहले {target} तक)",
        "roll_complete": "रोल {current}/{total} पूरा। {remaining} और {emoji} भेजें!",
        "normal_mode": "🎮 सामान्य मोड",
        "crazy_mode": "🔥 पागल मोड",
        "select_mode": "गेम मोड चुनें:",
        "select_rolls": "रोल की संख्या चुनें:",
        "select_target": "लक्ष्य स्कोर चुनें:",
        "game_created": "🎯 खेल बनाया गया! प्रतिद्वंद्वी की प्रतीक्षा में...",
        "usage_dice": "उपयोग: /dice <राशि>\nउदाहरण: /dice 5 या /dice all",
        "usage_darts": "उपयोग: /darts <राशि>\nउदाहरण: /darts 5 या /darts all",
        "usage_goal": "उपयोग: /goal <राशि>\nउदाहरण: /goal 5 या /goal all",
        "usage_bowl": "उपयोग: /bowl <राशि>\nउदाहरण: /bowl 5 या /bowl all",
    },
    "zh": {  # Mandarin Chinese
        "language_name": "中文 🇨🇳",
        # Welcome and Main Menu - RESTORED ORIGINAL FULL TEXT
        "welcome_title": "🎰 <b>欢迎来到Telegram赌场和托管机器人!</b> 🎰",
        "hello": "👋 您好 {first_name}!",
        "welcome_desc": "🎲 体验赌场游戏的刺激，或通过我们的自动化托管系统保护您的交易安全。",
        "ai_feature": "✨ 新功能：与我们的<b>AI助手</b>聊天，解答任何问题或任务！",
        "current_balance": "💰 当前余额：<b>{balance}</b>",
        "choose_option": "选择下方选项开始：",

        # Buttons
        "withdraw": "📤 提款",
        "games": "🎮 游戏",
        "more": "➕ 更多",
        "stats": "📊 统计",
        "settings": "⚙️ 设置",
        "help": "❓ 帮助",
        "bonuses": "🎁 奖金",
        "escrow": "🔐 托管",
        "ai_assistant": "🤖 AI助手",
        "back": "🔙 返回",
        "cancel": "❌ 取消",
        "confirm": "✅ 确认",

        # Balance and Currency
        "balance": "💰 您的余额: {balance}",
        "your_balance": "💰 您的余额: {balance}",
        "insufficient_balance": "❌ 余额不足。请充值以继续。",
        "locked_in_games": "+ {amount} 锁定在游戏中",

        # Betting
        "enter_bet_amount": "输入您的投注金额:",
        "bet_placed": "🎲 下注: ${amount:.2f}",
        "invalid_amount": "无效金额。请输入有效数字或'all'。",
        "min_bet": "此游戏的最小投注额为 {amount}",
        "max_bet": "此游戏的最大投注额为 {amount}",

        # Game Results
        "you_won": "🎉 您赢了{amount}!",
        "you_lost": "😔 您输了。祝下次好运!",
        "game_started": "🎮 游戏开始!",
        "game_ended": "🎮 游戏结束!",
        "round": "第{round}轮",
        "waiting_for_opponent": "⏳ 等待对手...",

        # Daily Bonus
        "daily_claim_success": "🎉 您已成功领取{amount}的每日奖金!",
        "daily_claim_wait": "⏳ 您已经领取了每日奖金。请等待{hours}小时{minutes}分钟后再次领取。",
        "daily_bonus": "🎁 每日奖金",

        # Achievements
        "achievement_unlocked": "🏅 <b>成就解锁!</b> 🏅\n\n您获得了<b>{emoji} {name}</b>徽章!\n<i>{description}</i>",
        "achievements": "🏅 成就",
        "no_achievements": "您还没有解锁任何成就。开始游戏以赚取徽章!",

        # Language
        "language_set": "✅ 语言已设置为中文",
        "select_language": "🌍 <b>选择您的语言:</b>",
        "language": "语言",

        # Games Menu
        "games_menu": "🎮 <b>赌场游戏</b>\n\n选择一个类别:",
        "dice_games": "🎲 骰子游戏",
        "card_games": "🃏 纸牌游戏",
        "original_games": "⭐ 原创游戏",
        "quick_games": "⚡ 快速游戏",

        # Settings
        "settings_menu": "⚙️ <b>设置</b>\n\n自定义您的体验:",
        "withdrawal_address": "💳 提款地址",
        "currency_settings": "💱 货币",
        "recovery_settings": "🔐 恢复",

        # Help
        "help_text": "❓ <b>帮助和命令</b>\n\n可用命令:\n/start - 主菜单\n/games - 浏览游戏\n/balance - 查看余额\n/withdraw - 提款\n/stats - 查看统计\n/daily - 领取每日奖金\n/help - 显示此帮助\n\n如需支持，请联系 @jashanxjagy",

        # Errors
        "error_occurred": "❌ 发生错误。请重试。",
        "command_not_found": "❌ 命令未找到。使用 /help 查看可用命令。",
        "maintenance_mode": "🛠️ <b>机器人维护中</b> 🛠️\n\n机器人目前正在进行计划维护。",
        "banned_user": "您已被禁止使用此机器人。",

        # Deposit/Withdrawal
        "withdrawal_menu": "📤 <b>提款</b>\n\n输入您要提款的金额:",
        "withdrawal_success": "✅ 提款请求已成功提交!",
        "withdrawal_pending": "您的提款正在处理中...",

        # Admin
        "admin_panel": "👑 <b>管理面板</b>",
        "admin_only": "此命令仅对管理员可用。",

        # Misc
        "coming_soon": "🚧 即将推出!",
        "feature_disabled": "此功能目前已禁用。",
        "loading": "⏳ 加载中...",
        "processing": "⏳ 处理中...",

        # Game-specific messages
        "dice_game": "🎲 骰子",
        "darts_game": "🎯 飞镖",
        "football_game": "⚽ 足球",
        "bowling_game": "🎳 保龄球",
        "blackjack_game": "🃏 二十一点",
        "roulette_game": "🎯 轮盘",
        "slots_game": "🎰 老虎机",
        "play_vs_bot": "🤖 与机器人对战",
        "play_vs_player": "👤 与玩家对战",
        "who_to_play": "您想与谁对战?",
        "bot_rolling": "机器人正在掷骰子...",
        "your_turn": "轮到您了! 发送 {rolls} {emoji}!",
        "bot_rolled": "机器人掷出: {rolls_text} = <b>{total}</b>",
        "you_rolled": "您掷出: {rolls_text} = <b>{total}</b>",
        "you_win_round": "您赢得本轮!",
        "bot_wins_round": "机器人赢得本轮!",
        "tie_round": "平局! 无分数。",
        "you_win_game": "🏆 恭喜! 您击败了机器人 ({user_score}-{bot_score}) 并赢得{amount}!",
        "bot_wins_game": "😔 机器人赢得比赛 ({bot_score}-{user_score})。您输了{amount}。",
        "score_update": "比分: 您 {user_score} - {bot_score} 机器人。(先到{target})",
        "roll_complete": "掷骰 {current}/{total} 完成。再发送 {remaining} 个 {emoji}!",
        "normal_mode": "🎮 普通模式",
        "crazy_mode": "🔥 疯狂模式",
        "select_mode": "选择游戏模式:",
        "select_rolls": "选择掷骰次数:",
        "select_target": "选择目标分数:",
        "game_created": "🎯 游戏已创建! 等待对手...",
        "usage_dice": "用法: /dice <金额>\n示例: /dice 5 或 /dice all",
        "usage_darts": "用法: /darts <金额>\n示例: /darts 5 或 /darts all",
        "usage_goal": "用法: /goal <金额>\n示例: /goal 5 或 /goal all",
        "usage_bowl": "用法: /bowl <金额>\n示例: /bowl 5 或 /bowl all",
    }
}

DEFAULT_LANG = "en"

class DepositDatabase:
    """SQLite database for deposit system"""

    def __init__(self, db_path=DEPOSITS_DB):
        self.db_path = db_path
        self._pool: asyncio.Queue | None = None
        self._pool_size = 10
        self.init_db()

    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    async def _init_pool(self):
        """Initialize the aiosqlite connection pool with PRAGMA settings."""
        if self._pool is not None:
            return
        self._pool = asyncio.Queue(maxsize=self._pool_size)
        for _ in range(self._pool_size):
            db = await aiosqlite.connect(self.db_path)
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.commit()
            await self._pool.put(db)
        logging.info(f"DepositDatabase aiosqlite pool initialized with {self._pool_size} connections")

    async def _get_conn(self):
        """Get a connection from the pool, initializing the pool if needed."""
        if self._pool is None:
            await self._init_pool()
        return await self._pool.get()

    async def _release_conn(self, db):
        """Return a connection to the pool."""
        await self._pool.put(db)

    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # User addresses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_addresses (
                user_id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                address_index INTEGER NOT NULL,
                eth_address TEXT,
                bnb_address TEXT,
                base_address TEXT,
                tron_address TEXT,
                solana_address TEXT,
                ton_address TEXT,
                ton_private_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: Add ton_private_key column if it doesn't exist
        try:
            cursor.execute("SELECT ton_private_key FROM user_addresses LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding ton_private_key column to user_addresses table")
            cursor.execute("ALTER TABLE user_addresses ADD COLUMN ton_private_key TEXT")
            conn.commit()

        # Migration: Add gas/sweep accounting columns (prevent gas-funding exploit)
        for col, definition in [
            ("last_native_balance", "REAL DEFAULT 0.0"),
        ]:
            try:
                cursor.execute(f"SELECT {col} FROM user_addresses LIMIT 1")
            except sqlite3.OperationalError:
                logging.info(f"Adding {col} column to user_addresses table")
                cursor.execute(f"ALTER TABLE user_addresses ADD COLUMN {col} {definition}")
                conn.commit()

        # Deposits table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                token TEXT,
                amount REAL NOT NULL,
                amount_usd REAL NOT NULL,
                from_address TEXT,
                to_address TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                confirmations INTEGER DEFAULT 0,
                block_number INTEGER,
                sweep_tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP,
                swept_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_addresses(user_id)
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_deposits_user ON deposits(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_deposits_status ON deposits(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_deposits_chain ON deposits(chain)')

        # Rains table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rains (
                rain_id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                creator_id INTEGER NOT NULL,
                creator_username TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                end_time TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'active'
            )
        ''')

        # Rain participants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rain_participants (
                rain_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                PRIMARY KEY (rain_id, user_id),
                FOREIGN KEY (rain_id) REFERENCES rains(rain_id)
            )
        ''')

        conn.commit()
        conn.close()
        logging.info("Deposit database initialized")

    def get_or_create_user(self, telegram_id):
        """Get or create user with unique address index"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT * FROM user_addresses WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()

        if user:
            conn.close()
            return {
                'user_id': user[0],
                'telegram_id': user[1],
                'address_index': user[2],
                'eth_address': user[3],
                'bnb_address': user[4],
                'base_address': user[5],
                'tron_address': user[6],
                'solana_address': user[7],
                'ton_address': user[8],
                'ton_private_key': user[9]
            }

        # Get next address index
        cursor.execute('SELECT MAX(address_index) FROM user_addresses')
        max_index = cursor.fetchone()[0]
        next_index = (max_index or 0) + 1

        # Generate addresses
        wallet_manager = HDWalletManager()
        addresses = {}
        ton_private_key = None
        for chain in ['ETH', 'BNB', 'BASE', 'TRON', 'SOLANA', 'TON']:
            try:
                if chain == 'TON':
                    # Generate TON address with private key
                    ton_data = wallet_manager.generate_ton_with_key(next_index)
                    if ton_data and isinstance(ton_data, dict) and 'address' in ton_data:
                        addresses[chain] = ton_data['address']
                        ton_private_key = ton_data.get('private_key')
                    else:
                        addresses[chain] = None
                        logging.warning(f"Failed to generate TON address for index {next_index} - TON library may not be available")
                else:
                    addresses[chain] = wallet_manager.generate_address(chain, next_index)
            except Exception as e:
                logging.error(f"Error generating {chain} address for index {next_index}: {e}")
                logging.error(traceback.format_exc())
                addresses[chain] = None

        # Insert new user
        cursor.execute('''
            INSERT INTO user_addresses
            (telegram_id, address_index, eth_address, bnb_address, base_address,
             tron_address, solana_address, ton_address, ton_private_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (telegram_id, next_index, addresses['ETH'], addresses['BNB'],
              addresses['BASE'], addresses['TRON'], addresses['SOLANA'], addresses['TON'], ton_private_key))

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logging.info(f"Created deposit addresses for user {telegram_id} with index {next_index}")

        return {
            'user_id': user_id,
            'telegram_id': telegram_id,
            'address_index': next_index,
            'eth_address': addresses['ETH'],
            'bnb_address': addresses['BNB'],
            'base_address': addresses['BASE'],
            'tron_address': addresses['TRON'],
            'solana_address': addresses['SOLANA'],
            'ton_address': addresses['TON'],
            'ton_private_key': ton_private_key
        }

    def add_deposit(self, tx_hash, user_id, chain, amount, amount_usd, to_address,
                    token=None, from_address=None, block_number=None):
        """Add new deposit"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO deposits
                (tx_hash, user_id, chain, token, amount, amount_usd, from_address,
                 to_address, block_number, status, confirmations)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
            ''', (tx_hash, user_id, chain, token, amount, amount_usd, from_address,
                  to_address, block_number))

            conn.commit()
            deposit_id = cursor.lastrowid
            logging.info(f"Added deposit {tx_hash} for user {user_id}")
            return deposit_id
        except sqlite3.IntegrityError:
            logging.warning(f"Deposit {tx_hash} already exists")
            return None
        finally:
            conn.close()

    def update_deposit_status(self, tx_hash, status, confirmations=None,
                              sweep_tx_hash=None, confirmed_at=None, swept_at=None):
        """Update deposit status"""
        conn = self.get_connection()
        cursor = conn.cursor()

        updates = ['status = ?']
        params = [status]

        if confirmations is not None:
            updates.append('confirmations = ?')
            params.append(confirmations)

        if sweep_tx_hash:
            updates.append('sweep_tx_hash = ?')
            params.append(sweep_tx_hash)

        if confirmed_at:
            updates.append('confirmed_at = ?')
            params.append(confirmed_at)

        if swept_at:
            updates.append('swept_at = ?')
            params.append(swept_at)

        params.append(tx_hash)

        cursor.execute(f'''
            UPDATE deposits SET {', '.join(updates)} WHERE tx_hash = ?
        ''', params)

        conn.commit()
        conn.close()

    def get_pending_deposits(self):
        """Get all pending deposits"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, tx_hash, user_id, chain, token, amount, amount_usd,
                   to_address, status, confirmations, block_number
            FROM deposits
            WHERE status IN ('pending', 'confirmed')
            ORDER BY created_at DESC
        ''')
        deposits = cursor.fetchall()
        conn.close()
        return deposits

    def get_user_deposits(self, telegram_id, limit=10):
        """Get user's recent deposits"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.tx_hash, d.chain, d.token, d.amount, d.amount_usd,
                   d.status, d.created_at, d.confirmed_at
            FROM deposits d
            JOIN user_addresses u ON d.user_id = u.user_id
            WHERE u.telegram_id = ?
            ORDER BY d.created_at DESC
            LIMIT ?
        ''', (telegram_id, limit))
        deposits = cursor.fetchall()
        conn.close()
        return deposits

    def get_user_by_address(self, address, chain):
        """Get user by deposit address"""
        # Validate chain to prevent SQL injection
        valid_chains = ['ETH', 'BNB', 'BASE', 'TRON', 'SOLANA', 'TON']
        if chain not in valid_chains:
            logging.error(f"Invalid chain: {chain}")
            return None

        conn = self.get_connection()
        cursor = conn.cursor()

        column = f"{chain.lower()}_address"
        cursor.execute(f'''
            SELECT user_id, telegram_id, address_index
            FROM user_addresses
            WHERE {column} = ?
        ''', (address,))

        user = cursor.fetchone()
        conn.close()

        if user:
            return {'user_id': user[0], 'telegram_id': user[1], 'address_index': user[2]}
        return None

    # ── Rain helpers ──────────────────────────────────────────────────────

    def create_rain(self, rain_id, chat_id, creator_id, creator_username, amount, currency, end_time):
        """Insert a new rain record. Returns True on success."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO rains (rain_id, chat_id, creator_id, creator_username, amount, currency, end_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            ''', (rain_id, chat_id, creator_id, creator_username, amount, currency, end_time))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"create_rain error: {e}")
            return False
        finally:
            conn.close()

    def set_rain_message_id(self, rain_id, message_id):
        """Store the message_id for the rain announcement message."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE rains SET message_id = ? WHERE rain_id = ?', (message_id, rain_id))
            conn.commit()
        finally:
            conn.close()

    def get_rain(self, rain_id):
        """Fetch a single rain row as a dict."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT rain_id, chat_id, message_id, creator_id, creator_username,
                   amount, currency, end_time, status
            FROM rains WHERE rain_id = ?
        ''', (rain_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        keys = ['rain_id', 'chat_id', 'message_id', 'creator_id', 'creator_username',
                'amount', 'currency', 'end_time', 'status']
        return dict(zip(keys, row))

    def add_rain_participant(self, rain_id, user_id, username):
        """Add a participant to a rain. Returns True if newly added, False if duplicate."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO rain_participants (rain_id, user_id, username)
                VALUES (?, ?, ?)
            ''', (rain_id, user_id, username))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already joined (UNIQUE constraint)
        finally:
            conn.close()

    def get_rain_participants(self, rain_id):
        """Return list of (user_id, username) tuples for a rain."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username FROM rain_participants WHERE rain_id = ?', (rain_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def complete_rain(self, rain_id):
        """Mark a rain as completed."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE rains SET status = 'completed' WHERE rain_id = ?", (rain_id,))
            conn.commit()
        finally:
            conn.close()

    # ── Async helpers (used by background tasks to avoid DB locking) ──────

    async def async_add_deposit(self, tx_hash, user_id, chain, amount, amount_usd,
                                to_address, token=None, from_address=None, block_number=None):
        """Async version of add_deposit using aiosqlite connection pool."""
        db = await self._get_conn()
        try:
            try:
                await db.execute('''
                    INSERT INTO deposits
                    (tx_hash, user_id, chain, token, amount, amount_usd, from_address,
                     to_address, block_number, status, confirmations)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
                ''', (tx_hash, user_id, chain, token, amount, amount_usd,
                      from_address, to_address, block_number))
                await db.commit()
                cursor = await db.execute("SELECT last_insert_rowid()")
                row = await cursor.fetchone()
                deposit_id = row[0] if row else None
                logging.info(f"Added deposit {tx_hash} for user {user_id}")
                return deposit_id
            except aiosqlite.IntegrityError:
                logging.warning(f"Deposit {tx_hash} already exists")
                return None
        except Exception as e:
            logging.error(f"async_add_deposit error: {e}")
            return None
        finally:
            await self._release_conn(db)

    async def async_update_deposit_status(self, tx_hash, status, confirmations=None,
                                          sweep_tx_hash=None, confirmed_at=None, swept_at=None):
        """Async version of update_deposit_status using aiosqlite connection pool."""
        db = await self._get_conn()
        try:
            updates = ['status = ?']
            params = [status]
            if confirmations is not None:
                updates.append('confirmations = ?')
                params.append(confirmations)
            if sweep_tx_hash:
                updates.append('sweep_tx_hash = ?')
                params.append(sweep_tx_hash)
            if confirmed_at:
                updates.append('confirmed_at = ?')
                params.append(confirmed_at)
            if swept_at:
                updates.append('swept_at = ?')
                params.append(swept_at)
            params.append(tx_hash)
            await db.execute(
                f"UPDATE deposits SET {', '.join(updates)} WHERE tx_hash = ?",
                params
            )
            await db.commit()
        except Exception as e:
            logging.error(f"async_update_deposit_status error: {e}")
        finally:
            await self._release_conn(db)

    async def async_get_recorded_unswept(self, user_id, chain, address, token=None):
        """Return sum of already-recorded unswept deposits for an address (async)."""
        db = await self._get_conn()
        try:
            if token is None:
                cursor = await db.execute('''
                    SELECT COALESCE(SUM(amount), 0) FROM deposits
                    WHERE user_id = ? AND chain = ? AND to_address = ? AND token IS NULL
                    AND status IN ('pending', 'confirmed')
                ''', (user_id, chain, address))
            else:
                cursor = await db.execute('''
                    SELECT COALESCE(SUM(amount), 0) FROM deposits
                    WHERE user_id = ? AND chain = ? AND to_address = ? AND token = ?
                    AND status IN ('pending', 'confirmed')
                ''', (user_id, chain, address, token))
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception as e:
            logging.error(f"async_get_recorded_unswept error: {e}")
            return 0.0
        finally:
            await self._release_conn(db)

    async def async_deposit_exists(self, tx_hash):
        """Return True if deposit with tx_hash already exists (async)."""
        db = await self._get_conn()
        try:
            cursor = await db.execute(
                'SELECT id FROM deposits WHERE tx_hash = ?', (tx_hash,)
            )
            return await cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"async_deposit_exists error: {e}")
            return False
        finally:
            await self._release_conn(db)

    async def async_get_all_user_addresses(self):
        """Return all rows from user_addresses as list of dicts (async)."""
        db = await self._get_conn()
        try:
            cursor = await db.execute(
                'SELECT user_id, telegram_id, address_index, eth_address, bnb_address, '
                'base_address, tron_address, solana_address, ton_address FROM user_addresses'
            )
            rows = await cursor.fetchall()
            return rows
        except Exception as e:
            logging.error(f"async_get_all_user_addresses error: {e}")
            return []
        finally:
            await self._release_conn(db)

    async def async_get_or_create_user(self, telegram_id: int) -> dict:
        """Async version of get_or_create_user using aiosqlite connection pool.

        Returns the same dict structure as the synchronous version.
        Address generation (CPU-bound) is still done synchronously but is
        only invoked for brand-new users so it does not block the loop
        in steady-state operation.
        """
        db = await self._get_conn()
        try:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM user_addresses WHERE telegram_id = ?', (telegram_id,)
            )
            user = await cursor.fetchone()

            if user:
                return {
                    'user_id': user['user_id'],
                    'telegram_id': user['telegram_id'],
                    'address_index': user['address_index'],
                    'eth_address': user['eth_address'],
                    'bnb_address': user['bnb_address'],
                    'base_address': user['base_address'],
                    'tron_address': user['tron_address'],
                    'solana_address': user['solana_address'],
                    'ton_address': user['ton_address'],
                    'ton_private_key': user['ton_private_key'],
                }

            # New user — generate addresses (sync, but only happens once per user)
            cursor2 = await db.execute('SELECT MAX(address_index) FROM user_addresses')
            row = await cursor2.fetchone()
            max_index = row[0] if row and row[0] is not None else 0
            next_index = max_index + 1

            wallet_manager = HDWalletManager()
            addresses = {}
            ton_private_key = None
            for chain in ['ETH', 'BNB', 'BASE', 'TRON', 'SOLANA', 'TON']:
                try:
                    if chain == 'TON':
                        ton_data = wallet_manager.generate_ton_with_key(next_index)
                        if ton_data and isinstance(ton_data, dict) and 'address' in ton_data:
                            addresses[chain] = ton_data['address']
                            ton_private_key = ton_data.get('private_key')
                        else:
                            addresses[chain] = None
                    else:
                        addresses[chain] = wallet_manager.generate_address(chain, next_index)
                except Exception as e:
                    logging.error(f"async_get_or_create_user: error generating {chain} address: {e}")
                    addresses[chain] = None

            await db.execute('''
                INSERT INTO user_addresses
                (telegram_id, address_index, eth_address, bnb_address, base_address,
                 tron_address, solana_address, ton_address, ton_private_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (telegram_id, next_index, addresses['ETH'], addresses['BNB'],
                  addresses['BASE'], addresses['TRON'], addresses['SOLANA'],
                  addresses['TON'], ton_private_key))
            await db.commit()

            cursor3 = await db.execute('SELECT last_insert_rowid()')
            row3 = await cursor3.fetchone()
            user_id = row3[0] if row3 else next_index

            logging.info(f"async_get_or_create_user: created deposit addresses for user {telegram_id} (index {next_index})")
            return {
                'user_id': user_id,
                'telegram_id': telegram_id,
                'address_index': next_index,
                'eth_address': addresses['ETH'],
                'bnb_address': addresses['BNB'],
                'base_address': addresses['BASE'],
                'tron_address': addresses['TRON'],
                'solana_address': addresses['SOLANA'],
                'ton_address': addresses['TON'],
                'ton_private_key': ton_private_key,
            }
        except Exception as e:
            logging.error(f"async_get_or_create_user error: {e}")
            # Fallback to synchronous version
            return self.get_or_create_user(telegram_id)
        finally:
            await self._release_conn(db)

    async def async_update_deposit_status_swept(self, tx_hash: str, sweep_tx_hash: str, swept_at: str):
        """Async helper to mark a deposit as swept (used by AutoSweeper)."""
        db = await self._get_conn()
        try:
            await db.execute(
                "UPDATE deposits SET status = 'swept', sweep_tx_hash = ?, swept_at = ? WHERE tx_hash = ?",
                (sweep_tx_hash, swept_at, tx_hash)
            )
            await db.commit()
        except Exception as e:
            logging.error(f"async_update_deposit_status_swept error: {e}")
        finally:
            await self._release_conn(db)

    # Whitelist mapping chain name → user_addresses column for that chain's deposit address.
    # Used to build safe SQL WHERE clauses without f-string injection risk.
    _CHAIN_ADDRESS_COL: dict = {
        'ETH': 'eth_address',
        'BNB': 'bnb_address',
        'BASE': 'base_address',
        'TRON': 'tron_address',
        'SOLANA': 'solana_address',
        'TON': 'ton_address',
    }

    async def async_get_last_native_balance(self, address: str, chain: str) -> float:
        """Return the stored baseline native balance for an address (baseline tracking model)."""
        col = self._CHAIN_ADDRESS_COL.get(chain)
        if not col:
            return 0.0
        db = await self._get_conn()
        try:
            cursor = await db.execute(
                f"SELECT COALESCE(last_native_balance, 0) FROM user_addresses WHERE {col} = ?",
                (address,)
            )
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception as e:
            logging.error(f"async_get_last_native_balance error: {e}")
            return 0.0
        finally:
            await self._release_conn(db)

    async def async_update_last_native_balance(self, address: str, chain: str, new_balance: float):
        """Persist the new baseline native balance for an address."""
        col = self._CHAIN_ADDRESS_COL.get(chain)
        if not col:
            return
        db = await self._get_conn()
        try:
            await db.execute(
                f"UPDATE user_addresses SET last_native_balance = ? WHERE {col} = ?",
                (new_balance, address)
            )
            await db.commit()
        except Exception as e:
            logging.error(f"async_update_last_native_balance error: {e}")
        finally:
            await self._release_conn(db)

    async def async_increment_last_native_balance(self, address: str, chain: str, delta: float):
        """Atomically add *delta* to last_native_balance (used after gas funding)."""
        col = self._CHAIN_ADDRESS_COL.get(chain)
        if not col:
            return
        db = await self._get_conn()
        try:
            await db.execute(
                f"UPDATE user_addresses "
                f"SET last_native_balance = COALESCE(last_native_balance, 0) + ? "
                f"WHERE {col} = ?",
                (delta, address)
            )
            await db.commit()
        except Exception as e:
            logging.error(f"async_increment_last_native_balance error: {e}")
        finally:
            await self._release_conn(db)

    async def async_lower_last_native_balance_if_less(self, address: str, chain: str, candidate: float):
        """Atomically set last_native_balance = candidate only if candidate < current value.

        Used after a sweep confirms to reflect the post-sweep on-chain balance without
        overwriting a higher baseline that may have been written by a concurrent deposit.
        """
        col = self._CHAIN_ADDRESS_COL.get(chain)
        if not col:
            return
        db = await self._get_conn()
        try:
            await db.execute(
                f"UPDATE user_addresses "
                f"SET last_native_balance = ? "
                f"WHERE {col} = ? AND COALESCE(last_native_balance, 0) > ?",
                (candidate, address, candidate)
            )
            await db.commit()
        except Exception as e:
            logging.error(f"async_lower_last_native_balance_if_less error: {e}")
        finally:
            await self._release_conn(db)

    async def async_get_user_deposits(self, telegram_id: int, limit: int = 10):
        """Async version of get_user_deposits using aiosqlite connection pool."""
        db = await self._get_conn()
        try:
            cursor = await db.execute('''
                SELECT d.tx_hash, d.chain, d.token, d.amount, d.amount_usd,
                       d.status, d.created_at, d.confirmed_at
                FROM deposits d
                JOIN user_addresses u ON d.user_id = u.user_id
                WHERE u.telegram_id = ?
                ORDER BY d.created_at DESC
                LIMIT ?
            ''', (telegram_id, limit))
            return await cursor.fetchall()
        except Exception as e:
            logging.error(f"async_get_user_deposits error: {e}")
            return []
        finally:
            await self._release_conn(db)


    # ── Async rain helpers (non-blocking for the event loop) ──────────────

    async def async_create_rain(self, rain_id, chat_id, creator_id, creator_username, amount, currency, end_time):
        """Async version of create_rain using aiosqlite connection pool."""
        db = await self._get_conn()
        try:
            await db.execute('''
                INSERT INTO rains (rain_id, chat_id, creator_id, creator_username, amount, currency, end_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            ''', (rain_id, chat_id, creator_id, creator_username, amount, currency, end_time))
            await db.commit()
            return True
        except Exception as e:
            logging.error(f"async_create_rain error: {e}")
            return False
        finally:
            await self._release_conn(db)

    async def async_set_rain_message_id(self, rain_id, message_id):
        """Async version of set_rain_message_id."""
        db = await self._get_conn()
        try:
            await db.execute('UPDATE rains SET message_id = ? WHERE rain_id = ?', (message_id, rain_id))
            await db.commit()
        except Exception as e:
            logging.error(f"async_set_rain_message_id error: {e}")
        finally:
            await self._release_conn(db)

    async def async_get_rain(self, rain_id):
        """Async version of get_rain."""
        db = await self._get_conn()
        try:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT rain_id, chat_id, message_id, creator_id, creator_username, '
                'amount, currency, end_time, status FROM rains WHERE rain_id = ?',
                (rain_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)
        except Exception as e:
            logging.error(f"async_get_rain error: {e}")
            return None
        finally:
            await self._release_conn(db)

    async def async_add_rain_participant(self, rain_id, user_id, username):
        """Async version of add_rain_participant."""
        db = await self._get_conn()
        try:
            try:
                await db.execute('''
                    INSERT INTO rain_participants (rain_id, user_id, username)
                    VALUES (?, ?, ?)
                ''', (rain_id, user_id, username))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
        except Exception as e:
            logging.error(f"async_add_rain_participant error: {e}")
            return False
        finally:
            await self._release_conn(db)

    async def async_get_rain_participants(self, rain_id):
        """Async version of get_rain_participants."""
        db = await self._get_conn()
        try:
            cursor = await db.execute(
                'SELECT user_id, username FROM rain_participants WHERE rain_id = ?',
                (rain_id,)
            )
            return await cursor.fetchall()
        except Exception as e:
            logging.error(f"async_get_rain_participants error: {e}")
            return []
        finally:
            await self._release_conn(db)

    async def async_complete_rain(self, rain_id):
        """Async version of complete_rain."""
        db = await self._get_conn()
        try:
            await db.execute("UPDATE rains SET status = 'completed' WHERE rain_id = ?", (rain_id,))
            await db.commit()
        except Exception as e:
            logging.error(f"async_complete_rain error: {e}")
        finally:
            await self._release_conn(db)

    async def async_get_active_rains(self, chat_id=None):
        """Get all active rains, optionally filtered by chat_id."""
        db = await self._get_conn()
        try:
            if chat_id:
                cursor = await db.execute(
                    'SELECT rain_id, chat_id, message_id, creator_id, creator_username, '
                    'amount, currency, end_time, status FROM rains WHERE status = ? AND chat_id = ?',
                    ('active', chat_id)
                )
            else:
                cursor = await db.execute(
                    'SELECT rain_id, chat_id, message_id, creator_id, creator_username, '
                    'amount, currency, end_time, status FROM rains WHERE status = ?',
                    ('active',)
                )
            return await cursor.fetchall()
        except Exception as e:
            logging.error(f"async_get_active_rains error: {e}")
            return []
        finally:
            await self._release_conn(db)

class HDWalletManager:
    """HD Wallet Manager for multi-chain address generation"""

    def __init__(self):
        self.mnemonic = MASTER_MNEMONIC
        self.seed = Bip39SeedGenerator(self.mnemonic).Generate()

    def generate_address(self, chain, index):
        """Generate address for specific chain and index"""
        if chain in ['ETH', 'BNB', 'BASE']:
            return self._generate_evm_address(chain, index)
        elif chain == 'TRON':
            return self._generate_tron_address(index)
        elif chain == 'SOLANA':
            return self._generate_solana_address(index)
        elif chain == 'TON':
            return self._generate_ton_address(index)
        else:
            raise ValueError(f"Unsupported chain: {chain}")

    def derive_private_key(self, chain, index):
        """Derive private key for specific chain and index"""
        if chain in ['ETH', 'BNB', 'BASE']:
            return self._derive_evm_private_key(index)
        elif chain == 'TRON':
            return self._derive_tron_private_key(index)
        elif chain == 'SOLANA':
            return self._derive_solana_private_key(index)
        elif chain == 'TON':
            return self._derive_ton_private_key(index)
        else:
            raise ValueError(f"Unsupported chain: {chain}")

    def _generate_evm_address(self, chain, index):
        """Generate EVM address (ETH, BNB, BASE)"""
        bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.ETHEREUM)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        return bip44_acc.PublicKey().ToAddress()

    def _derive_evm_private_key(self, index):
        """Derive EVM private key"""
        bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.ETHEREUM)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        return bip44_acc.PrivateKey().Raw().ToHex()

    def _generate_tron_address(self, index):
        """Generate TRON address"""
        if not TRON_AVAILABLE:
            return None
        bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.TRON)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        return bip44_acc.PublicKey().ToAddress()

    def _derive_tron_private_key(self, index):
        """Derive TRON private key"""
        bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.TRON)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
        return bip44_acc.PrivateKey().Raw().ToHex()

    def _generate_solana_address(self, index):
        """Generate Solana address"""
        if not SOLANA_AVAILABLE:
            return None
        try:
            bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.SOLANA)
            bip44_acc = bip44_ctx.Purpose().Coin().Account(index).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
            # Solana uses Ed25519, get the public key bytes directly
            pub_key_bytes = bip44_acc.PublicKey().RawCompressed().ToBytes()
            return base58.b58encode(pub_key_bytes).decode('utf-8')
        except Exception as e:
            logging.error(f"Error generating Solana address: {e}")
            return None

    def _derive_solana_private_key(self, index):
        """Derive Solana private key"""
        bip44_ctx = Bip44.FromSeed(self.seed, Bip44Coins.SOLANA)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(index).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
        # Return the full 64-byte keypair (32 bytes private + 32 bytes public)
        priv_key_bytes = bip44_acc.PrivateKey().Raw().ToBytes()
        pub_key_bytes = bip44_acc.PublicKey().RawCompressed().ToBytes()
        return priv_key_bytes + pub_key_bytes

    def generate_ton_with_key(self, index):
        """Generate TON address with separate private key (TON doesn't use BIP44 properly)"""
        if not TON_AVAILABLE:
            return None
        try:
            # Generate a deterministic private key for TON using HMAC-SHA256
            # This is more secure than simple SHA256 as it uses the mnemonic as a key

            # Use HMAC with mnemonic as key and index as message for key derivation
            message = f"ton-deposit:{index}".encode('utf-8')
            priv_key_bytes = hmac.new(
                self.mnemonic.encode('utf-8'),
                message,
                hashlib.sha256
            ).digest()

            # Derive public key from private key
            pub_key_bytes = private_key_to_public_key(priv_key_bytes)

            # Create TON address (workchain 0, non-bounceable)
            address = TonAddress((0, pub_key_bytes))
            address_str = address.to_str(is_bounceable=False, is_url_safe=True, is_test_only=False)

            # Store private key as hex string
            private_key_hex = priv_key_bytes.hex()

            return {
                'address': address_str,
                'private_key': private_key_hex
            }
        except Exception as e:
            logging.error(f"Error generating TON address with key: {e}")
            return None

    def _generate_ton_address(self, index):
        """Generate TON address (deprecated - use generate_ton_with_key)"""
        ton_data = self.generate_ton_with_key(index)
        return ton_data['address'] if ton_data else None

    def _derive_ton_private_key(self, index):
        """Derive TON private key (deprecated - use generate_ton_with_key)"""
        ton_data = self.generate_ton_with_key(index)
        return bytes.fromhex(ton_data['private_key']) if ton_data else None

class EvmService:
    """Service for EVM chains (ETH, BNB, BASE)"""

    def __init__(self, chain):
        self.chain = chain
        self.rpc_urls = RPC_ENDPOINTS[chain]
        self.current_rpc_index = 0
        self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_urls[self.current_rpc_index]))
        self.master_wallet = MASTER_WALLETS[chain]

    def _rotate_rpc(self):
        """Rotate to the next RPC endpoint."""
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
        self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_urls[self.current_rpc_index]))
        logging.info(f"{self.chain}: switched to RPC {self.rpc_urls[self.current_rpc_index]}")

    async def _execute_with_fallback(self, func, *args):
        """Execute an async Web3 call with RPC fallback on failure."""
        last_exc = None
        for attempt in range(len(self.rpc_urls)):
            try:
                return await func(*args)
            except Exception as e:
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("429", "rate limit", "timeout", "connection", "network")):
                    logging.warning(f"{self.chain} RPC error on {self.rpc_urls[self.current_rpc_index]}: {e}. Rotating RPC.")
                    self._rotate_rpc()
                    last_exc = e
                else:
                    raise
        logging.error(f"{self.chain}: all {len(self.rpc_urls)} RPCs failed. Last error: {last_exc}")
        return None

    async def _fetch_gas_price(self):
        return await self.w3.eth.gas_price

    async def _fetch_chain_id(self):
        return await self.w3.eth.chain_id

    async def _fetch_block_number(self):
        return await self.w3.eth.block_number

    async def get_balance(self, address):
        """Get native token balance"""
        try:
            balance_wei = await self._execute_with_fallback(self.w3.eth.get_balance, address)
            if balance_wei is None:
                return 0.0
            balance = Web3.from_wei(balance_wei, 'ether')
            return float(balance)
        except Exception as e:
            logging.error(f"Error getting {self.chain} balance for {address}: {e}")
            return 0.0

    async def get_token_balance(self, address, token_contract, decimals):
        """Get ERC20 token balance"""
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_contract),
                abi=[{
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }]
            )
            balance = await self._execute_with_fallback(
                contract.functions.balanceOf(Web3.to_checksum_address(address)).call
            )
            if balance is None:
                return 0.0
            return balance / (10 ** decimals)
        except Exception as e:
            logging.error(f"Error getting token balance: {e}")
            return 0.0

    async def sweep(self, from_address, private_key, amount=None):
        """Sweep native tokens to master wallet"""
        try:
            account = Account.from_key(private_key)

            # Get balance
            balance = await self.get_balance(from_address)
            if balance == 0:
                return None

            # Get gas price
            gas_price = await self._execute_with_fallback(self._fetch_gas_price)
            if gas_price is None:
                return None
            gas_limit = 21000
            gas_cost = Web3.from_wei(gas_price * gas_limit, 'ether')

            # Calculate amount to send
            if amount is None:
                amount = balance - float(gas_cost)

            if amount <= 0:
                logging.warning(f"Insufficient balance for gas on {self.chain}")
                return None

            # Build transaction
            nonce = await self._execute_with_fallback(self.w3.eth.get_transaction_count, from_address)
            chain_id = await self._execute_with_fallback(self._fetch_chain_id)
            tx = {
                'from': Web3.to_checksum_address(from_address),
                'to': Web3.to_checksum_address(self.master_wallet),
                'value': Web3.to_wei(amount, 'ether'),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': chain_id
            }

            # Sign and send
            signed = self.w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = await self._execute_with_fallback(
                self.w3.eth.send_raw_transaction, signed.rawTransaction
            )
            if tx_hash is None:
                return None

            logging.info(f"Swept {amount} {self.chain} from {from_address} - TX: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logging.error(f"Error sweeping {self.chain}: {e}")
            return None

    async def sweep_token(self, from_address, private_key, token_contract, decimals):
        """Sweep ERC20 tokens to master wallet"""
        try:
            account = Account.from_key(private_key)

            # Get token balance
            balance = await self.get_token_balance(from_address, token_contract, decimals)
            if balance == 0:
                return None

            # ERC20 transfer ABI
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_contract),
                abi=[{
                    "constant": False,
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                }]
            )

            # Build transaction
            amount_wei = int(balance * (10 ** decimals))
            gas_price = await self._execute_with_fallback(self._fetch_gas_price)
            nonce = await self._execute_with_fallback(self.w3.eth.get_transaction_count, from_address)
            chain_id = await self._execute_with_fallback(self._fetch_chain_id)
            tx = await contract.functions.transfer(
                Web3.to_checksum_address(self.master_wallet),
                amount_wei
            ).build_transaction({
                'from': Web3.to_checksum_address(from_address),
                'gas': 100000,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': chain_id
            })

            # Sign and send
            signed = self.w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = await self._execute_with_fallback(
                self.w3.eth.send_raw_transaction, signed.rawTransaction
            )
            if tx_hash is None:
                return None

            logging.info(f"Swept {balance} tokens from {from_address} - TX: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logging.error(f"Error sweeping token: {e}")
            return None

    async def fund_gas(self, to_address, amount):
        """Fund address with gas for token transfer"""
        try:
            hot_wallet = Account.from_key(HOT_WALLET_PRIVATE_KEY)

            gas_price = await self._execute_with_fallback(self._fetch_gas_price)
            nonce = await self._execute_with_fallback(self.w3.eth.get_transaction_count, hot_wallet.address)
            chain_id = await self._execute_with_fallback(self._fetch_chain_id)
            tx = {
                'from': hot_wallet.address,
                'to': Web3.to_checksum_address(to_address),
                'value': Web3.to_wei(amount, 'ether'),
                'gas': 21000,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': chain_id
            }

            signed = self.w3.eth.account.sign_transaction(tx, HOT_WALLET_PRIVATE_KEY)
            tx_hash = await self._execute_with_fallback(
                self.w3.eth.send_raw_transaction, signed.rawTransaction
            )
            if tx_hash is None:
                return None

            logging.info(f"Funded {to_address} with {amount} {self.chain} - TX: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logging.error(f"Error funding gas: {e}")
            return None

    async def scan_address(self, address, last_block=None):
        """Scan address for new transactions using getLogs (event-based, more efficient)"""
        try:
            current_block = await self._execute_with_fallback(self._fetch_block_number)
            if current_block is None:
                return [], None

            # Limit scan range to prevent timeout (max 1000 blocks)
            start_block = last_block + 1 if last_block else max(0, current_block - 100)
            if current_block - start_block > 1000:
                start_block = current_block - 1000

            transactions = []

            # For native transfers, we'd need to scan blocks or use a block explorer API
            # This is a simplified version - production should use Etherscan/block explorer API
            # or maintain an indexer

            # Check current balance only (simplified approach)
            balance = await self.get_balance(address)
            if balance > 0.0001:
                transactions.append({
                    'tx_hash': f"balance_check_{address}_{current_block}",
                    'from': None,
                    'to': address,
                    'value': balance,
                    'block_number': current_block,
                    'token': None
                })

            return transactions, current_block

        except Exception as e:
            logging.error(f"Error scanning address: {e}")
            return [], None

    async def get_erc20_deposits(self, address, token_contract, decimals, from_block, to_block):
        """Get incoming ERC20 Transfer events to address in block range using eth_getLogs"""
        try:
            TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
            # Pad address to 32-byte topic (left-pad with zeros)
            padded_address = "0x" + address.lower().replace("0x", "").zfill(64)

            logs = await self._execute_with_fallback(
                self.w3.eth.get_logs,
                {
                    'fromBlock': from_block,
                    'toBlock': to_block,
                    'address': Web3.to_checksum_address(token_contract),
                    'topics': [TRANSFER_TOPIC, None, padded_address]
                }
            )
            if logs is None:
                return []

            transfers = []
            for log in logs:
                # log['data'] is HexBytes in web3.py; convert to int via hex string
                amount_wei = int(log['data'].hex(), 16)
                amount = amount_wei / (10 ** decimals)
                transfers.append({
                    'tx_hash': log['transactionHash'].hex(),
                    'block_number': log['blockNumber'],
                    'amount': amount,
                })
            return transfers
        except Exception as e:
            logging.error(f"Error getting ERC20 deposits for {address} on {self.chain}: {e}")
            return []

    async def wait_for_receipt(self, tx_hash, timeout=120):
        """Wait for a transaction to be mined"""
        return await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

class TronService:
    """Service for TRON blockchain"""

    def __init__(self):
        if not TRON_AVAILABLE:
            raise ImportError("TRON library not available")
        self.chain = "TRON"
        self.rpc_urls = RPC_ENDPOINTS['TRON']
        self.current_rpc_index = 0
        # Fix for newer tronpy API - use provider instead of full_node
        try:
            from tronpy import AsyncTron
            self.tron = AsyncTron()
        except:
            self.tron = Tron()
        self.master_wallet = MASTER_WALLETS['TRON']

    def _rotate_rpc(self):
        """Rotate to the next TRON RPC endpoint."""
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
        try:
            from tronpy import AsyncTron
            self.tron = AsyncTron()
        except:
            self.tron = Tron()
        logging.info(f"TRON: switched to RPC {self.rpc_urls[self.current_rpc_index]}")

    async def _execute_with_fallback(self, func, *args):
        """Execute a synchronous tronpy call in an executor with RPC fallback."""
        loop = asyncio.get_event_loop()
        last_exc = None
        for attempt in range(len(self.rpc_urls)):
            try:
                return await loop.run_in_executor(None, func, *args)
            except Exception as e:
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("429", "rate limit", "timeout", "connection", "network")):
                    logging.warning(f"TRON RPC error on {self.rpc_urls[self.current_rpc_index]}: {e}. Rotating RPC.")
                    self._rotate_rpc()
                    last_exc = e
                else:
                    raise
        logging.error(f"TRON: all {len(self.rpc_urls)} RPCs failed. Last error: {last_exc}")
        return None

    async def get_balance(self, address):
        """Get TRX balance"""
        try:
            balance = await self._execute_with_fallback(self.tron.get_account_balance, address)
            return balance if balance else 0.0
        except Exception as e:
            logging.error(f"Error getting TRON balance: {e}")
            return 0.0

    async def get_token_balance(self, address, token_contract):
        """Get TRC20 token balance"""
        try:
            def _get_token_bal():
                contract = self.tron.get_contract(token_contract)
                balance = contract.functions.balanceOf(address)
                decimals = contract.functions.decimals()
                return balance / (10 ** decimals)
            result = await self._execute_with_fallback(_get_token_bal)
            return result if result is not None else 0.0
        except Exception as e:
            logging.error(f"Error getting TRON token balance: {e}")
            return 0.0

    async def sweep(self, from_address, private_key):
        """Sweep TRX to master wallet"""
        try:
            priv_key = TronPrivateKey(bytes.fromhex(private_key))
            balance = await self.get_balance(from_address)

            if balance < 1:  # Minimum 1 TRX
                return None

            # Reserve some TRX for fees
            amount = balance - 1.1
            master_wallet = self.master_wallet

            def _do_sweep():
                tx = (
                    self.tron.trx.transfer(from_address, master_wallet, int(amount * 1_000_000))
                    .build()
                    .sign(priv_key)
                )
                return tx.broadcast()

            result = await self._execute_with_fallback(_do_sweep)

            if result and result.get('result'):
                tx_hash = result.get('txid')
                logging.info(f"Swept {amount} TRX from {from_address} - TX: {tx_hash}")
                return tx_hash
            return None

        except Exception as e:
            logging.error(f"Error sweeping TRON: {e}")
            return None

    async def sweep_token(self, from_address, private_key, token_contract):
        """Sweep TRC20 tokens to master wallet"""
        try:
            priv_key = TronPrivateKey(bytes.fromhex(private_key))
            balance = await self.get_token_balance(from_address, token_contract)
            if balance == 0:
                return None

            master_wallet = self.master_wallet

            def _do_token_sweep():
                contract = self.tron.get_contract(token_contract)
                decimals = contract.functions.decimals()
                amount = int(balance * (10 ** decimals))
                tx = (
                    contract.functions.transfer(master_wallet, amount)
                    .with_owner(from_address)
                    .fee_limit(50_000_000)
                    .build()
                    .sign(priv_key)
                )
                return tx.broadcast()

            result = await self._execute_with_fallback(_do_token_sweep)

            if result and result.get('result'):
                tx_hash = result.get('txid')
                logging.info(f"Swept {balance} tokens from {from_address} - TX: {tx_hash}")
                return tx_hash
            return None

        except Exception as e:
            logging.error(f"Error sweeping TRON token: {e}")
            return None

    async def fund_gas(self, to_address, amount=15):
        """Fund address with TRX for fees"""
        try:
            hot_priv_key = TronPrivateKey(bytes.fromhex(HOT_WALLET_PRIVATE_KEY.replace('0x', '')))
            hot_address = hot_priv_key.public_key.to_base58check_address()

            def _do_fund():
                tx = (
                    self.tron.trx.transfer(hot_address, to_address, int(amount * 1_000_000))
                    .build()
                    .sign(hot_priv_key)
                )
                return tx.broadcast()

            result = await self._execute_with_fallback(_do_fund)

            if result and result.get('result'):
                return result.get('txid')
            return None

        except Exception as e:
            logging.error(f"Error funding TRON gas: {e}")
            return None

class SolanaService:
    """Service for Solana blockchain"""

    def __init__(self):
        if not SOLANA_AVAILABLE:
            raise ImportError("Solana library not available")
        self.chain = "SOLANA"
        self.rpc_urls = RPC_ENDPOINTS['SOLANA']
        self.current_rpc_index = 0
        self.master_wallet = MASTER_WALLETS['SOLANA']

    def _rotate_rpc(self):
        """Rotate to the next Solana RPC endpoint."""
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
        logging.info(f"SOLANA: switched to RPC {self.rpc_urls[self.current_rpc_index]}")

    async def _execute_with_fallback(self, coro_func, *args):
        """Execute an async Solana client call with RPC fallback."""
        last_exc = None
        for attempt in range(len(self.rpc_urls)):
            rpc_url = self.rpc_urls[self.current_rpc_index]
            try:
                async with SolanaClient(rpc_url) as client:
                    return await coro_func(client, *args)
            except Exception as e:
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("429", "rate limit", "timeout", "connection", "network")):
                    logging.warning(f"SOLANA RPC error on {rpc_url}: {e}. Rotating RPC.")
                    self._rotate_rpc()
                    last_exc = e
                else:
                    raise
        logging.error(f"SOLANA: all {len(self.rpc_urls)} RPCs failed. Last error: {last_exc}")
        return None

    async def get_balance(self, address):
        """Get SOL balance"""
        try:
            pubkey = SoldersPubkey.from_string(address)
            async def _get(client):
                response = await client.get_balance(pubkey)
                return response.value / 1e9 if response.value else 0.0
            result = await self._execute_with_fallback(_get)
            return result if result is not None else 0.0
        except Exception as e:
            logging.error(f"Error getting Solana balance: {e}")
            return 0.0

    async def get_token_balance(self, address, mint_address):
        """Get SPL token balance"""
        try:
            pubkey = SoldersPubkey.from_string(address)
            mint_pubkey = SoldersPubkey.from_string(mint_address)
            async def _get(client):
                response = await client.get_token_accounts_by_owner(
                    pubkey,
                    {"mint": mint_pubkey}
                )
                if response.value:
                    import struct
                    for account in response.value:
                        data = account.account.data
                        # SPL token account layout: amount is at offset 64, 8 bytes
                        amount = struct.unpack('<Q', data[64:72])[0]
                        decimals = TOKEN_CONTRACTS['SOLANA'].get('USDT', {}).get('decimals', 6)
                        return amount / (10 ** decimals)
                return 0.0
            result = await self._execute_with_fallback(_get)
            return result if result is not None else 0.0
        except Exception as e:
            logging.error(f"Error getting Solana token balance: {e}")
            return 0.0

    async def sweep(self, from_address, private_key_bytes):
        """Sweep SOL to master wallet"""
        try:
            from_keypair = SoldersKeypair.from_bytes(private_key_bytes)
            master_wallet = self.master_wallet

            async def _do_sweep(client):
                balance_response = await client.get_balance(from_keypair.pubkey())
                balance_lamports = balance_response.value
                if balance_lamports < 10000:
                    return None
                amount = balance_lamports - 5000
                transfer_ix = solders_transfer(
                    SoldersTransferParams(
                        from_pubkey=from_keypair.pubkey(),
                        to_pubkey=SoldersPubkey.from_string(master_wallet),
                        lamports=amount
                    )
                )
                blockhash_response = await client.get_latest_blockhash()
                recent_blockhash = blockhash_response.value.blockhash
                tx = SoldersTransaction.new_with_payer([transfer_ix], from_keypair.pubkey())
                tx.partial_sign([from_keypair], recent_blockhash)
                result = await client.send_transaction(tx)
                return str(result.value)

            tx_hash = await self._execute_with_fallback(_do_sweep)
            if tx_hash:
                logging.info(f"Swept SOL from {from_address} - TX: {tx_hash}")
            return tx_hash

        except Exception as e:
            logging.error(f"Error sweeping Solana: {e}")
            return None

    async def fund_gas(self, to_address, amount=0.001):
        """Fund address with SOL for fees"""
        try:
            hot_priv_bytes = bytes.fromhex(HOT_WALLET_PRIVATE_KEY.replace('0x', ''))
            if len(hot_priv_bytes) == 32:
                hot_keypair = SoldersKeypair.from_seed(hot_priv_bytes)
            else:
                hot_keypair = SoldersKeypair.from_bytes(hot_priv_bytes)

            async def _do_fund(client):
                transfer_ix = solders_transfer(
                    SoldersTransferParams(
                        from_pubkey=hot_keypair.pubkey(),
                        to_pubkey=SoldersPubkey.from_string(to_address),
                        lamports=int(amount * 1e9)
                    )
                )
                blockhash_response = await client.get_latest_blockhash()
                recent_blockhash = blockhash_response.value.blockhash
                tx = SoldersTransaction.new_with_payer([transfer_ix], hot_keypair.pubkey())
                tx.partial_sign([hot_keypair], recent_blockhash)
                result = await client.send_transaction(tx)
                return str(result.value)

            return await self._execute_with_fallback(_do_fund)

        except Exception as e:
            logging.error(f"Error funding Solana gas: {e}")
            return None

class TonService:
    """Service for TON blockchain"""

    def __init__(self):
        if not TON_AVAILABLE:
            raise ImportError("TON library not available")
        self.chain = "TON"
        self.rpc_url = RPC_ENDPOINTS['TON']
        self.master_wallet = MASTER_WALLETS['TON']

    async def get_balance(self, address):
        """Get TON balance"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.rpc_url}/getAddressBalance",
                    params={"address": address}
                )
                data = response.json()
                if data.get('ok'):
                    balance = int(data['result']) / 1e9
                    return balance
                return 0.0
        except Exception as e:
            logging.error(f"Error getting TON balance: {e}")
            return 0.0

    async def sweep(self, from_address, private_key):
        """Sweep TON to master wallet"""
        try:
            # TON sweep implementation
            # Note: Full implementation requires pytoniq or ton libraries
            balance = await self.get_balance(from_address)

            if balance < 0.1:  # Minimum 0.1 TON
                return None

            # Reserve for fees
            amount = balance - 0.05

            # This is a simplified version - production needs full TON wallet contract
            logging.warning("TON sweep requires full wallet contract implementation")
            return None

        except Exception as e:
            logging.error(f"Error sweeping TON: {e}")
            return None

class BlockMonitor:
    """Monitors blockchain for new deposits"""

    def __init__(self, db: DepositDatabase):
        self.db = db
        self.services = {}
        self.last_scanned_blocks = {}

        # Initialize services
        for chain in ['ETH', 'BNB', 'BASE']:
            try:
                self.services[chain] = EvmService(chain)
            except (ImportError, ConnectionError, ValueError) as e:
                logging.error(f"Error initializing {chain} service: {e}")

        try:
            self.services['TRON'] = TronService()
        except (ImportError, ConnectionError, ValueError) as e:
            logging.error(f"Error initializing TRON service: {e}")

        try:
            self.services['SOLANA'] = SolanaService()
        except (ImportError, ConnectionError, ValueError) as e:
            logging.error(f"Error initializing Solana service: {e}")

        try:
            self.services['TON'] = TonService()
        except (ImportError, ConnectionError, ValueError) as e:
            logging.error(f"Error initializing TON service: {e}")

    async def scan_all_addresses(self):
        """Scan all user addresses for deposits"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Get all user addresses
            cursor.execute('SELECT user_id, telegram_id, address_index, eth_address, bnb_address, base_address, tron_address, solana_address, ton_address FROM user_addresses')
            users = cursor.fetchall()
            conn.close()

            for user in users:
                user_id, telegram_id, index, eth_addr, bnb_addr, base_addr, tron_addr, sol_addr, ton_addr = user

                addresses = {
                    'ETH': eth_addr,
                    'BNB': bnb_addr,
                    'BASE': base_addr,
                    'TRON': tron_addr,
                    'SOLANA': sol_addr,
                    'TON': ton_addr
                }

                for chain, address in addresses.items():
                    if address and chain in self.services:
                        await self._scan_address(chain, address, user_id, telegram_id)
                        # Add small delay to prevent rate limiting
                        await asyncio.sleep(0.1)
                # Throttle between users to preserve RPC compute units
                await asyncio.sleep(0.5)

        except Exception as e:
            logging.error(f"Error in scan_all_addresses: {e}")

    async def scan_address(self, chain, address, user_id, telegram_id, bot=None):
        """Scan single address for deposits - Public interface. Returns True if new deposit found."""
        return await self._scan_address(chain, address, user_id, telegram_id, bot=bot)

    async def _scan_address(self, chain, address, user_id, telegram_id, bot=None):
        """Scan single address for deposits. Returns True if a new deposit was detected."""
        # Map each chain to its native coin symbol
        NATIVE_SYMBOLS = {
            'ETH': 'ETH',
            'BNB': 'BNB',
            'BASE': 'ETH',
            'TRON': 'TRX',
            'SOLANA': 'SOL',
            'TON': 'TON',
        }
        found_deposit = False
        try:
            service = self.services.get(chain)
            if not service:
                return False

            # ── Native balance delta (baseline tracking model) ──────────────
            # Compare current on-chain balance against the stored baseline.
            # The baseline is updated every time a new deposit is credited or
            # after a sweep confirms, so gas fees and sweep dust are handled
            # correctly without under-crediting the user.
            balance = await service.get_balance(address)

            last_native_balance = await self.db.async_get_last_native_balance(address, chain)
            new_native_amount = balance - last_native_balance
            if new_native_amount > 0.0001:  # Minimum threshold (native units)
                symbol = NATIVE_SYMBOLS.get(chain, chain)
                price_usd = await get_crypto_price_usd(symbol)
                amount_usd = new_native_amount * price_usd
                tx_hash = f"native_{chain}_{address}_{int(datetime.now().timestamp())}"

                deposit_id = await self.db.async_add_deposit(
                    tx_hash=tx_hash,
                    user_id=user_id,
                    chain=chain,
                    amount=new_native_amount,
                    amount_usd=amount_usd,
                    to_address=address
                )

                if deposit_id:
                    found_deposit = True
                    # Advance baseline to current balance now that the deposit is recorded
                    await self.db.async_update_last_native_balance(address, chain, balance)
                    logging.info(f"New native deposit: {new_native_amount} {symbol} for user {telegram_id} (${amount_usd:.2f})")
                    required_confs = CONFIRMATIONS.get(chain, 10)
                    await self.db.async_update_deposit_status(tx_hash, 'confirmed', confirmations=required_confs)

                    if telegram_id in user_wallets:
                        credit_wallet_crypto(telegram_id, new_native_amount, symbol)
                        if telegram_id in user_stats:
                            user_stats[telegram_id]["unwagered_deposit"] = (
                                user_stats[telegram_id].get("unwagered_deposit", 0.0) + amount_usd
                            )

                        # Referral deposit commission (0.5%)
                        if telegram_id in user_stats:
                            ref_data = user_stats[telegram_id].get('referral', {})
                            referrer_id = ref_data.get('referrer_id')
                            if referrer_id and referrer_id in user_stats:
                                commission = new_native_amount * 0.005
                                ref_dict = user_stats[referrer_id].setdefault('referral', {})
                                comm_dict = ref_dict.setdefault('commissions', {})
                                comm_dict[symbol] = comm_dict.get(symbol, 0.0) + commission
                                save_user_data(referrer_id)
                                logging.info(f"Credited {commission} {symbol} deposit commission to referrer {referrer_id}")

                        save_user_data(telegram_id)
                        logging.info(f"Credited {new_native_amount} {symbol} to user {telegram_id}")

                    if bot:
                        try:
                            await bot.send_message(
                                chat_id=telegram_id,
                                text=(
                                    f"{pe('win')} <b>Deposit Received!</b>\n\n"
                                    f"{pe('check')} <b>{new_native_amount:.6f} {symbol}</b> (${amount_usd:.2f}) "
                                    f"detected on {chain} and credited to your balance!"
                                ),
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as notify_err:
                            logging.warning(f"Could not notify user {telegram_id}: {notify_err}")

            # ── Token deposits ───────────────────────────────────────────────
            if chain in TOKEN_CONTRACTS:
                for token_name, token_info in TOKEN_CONTRACTS[chain].items():

                    # EVM chains: use Transfer event logs so each tx is tracked individually
                    if chain in ('ETH', 'BNB', 'BASE') and hasattr(service, 'get_erc20_deposits'):
                        track_key = (chain, address, token_name)
                        # Use the async fetch_block_number to avoid blocking the event loop
                        current_block = await service._execute_with_fallback(service._fetch_block_number)
                        if current_block is None:
                            continue
                        from_block = self.last_scanned_blocks.get(track_key)
                        if from_block is None:
                            # First scan – look back ~100 blocks to avoid re-crediting old deposits
                            from_block = max(0, current_block - 100)
                        else:
                            from_block = from_block + 1

                        if from_block <= current_block:
                            # ── Batch into ≤1000-block chunks to avoid RPC range limits ──
                            chunk_start = from_block
                            BATCH_SIZE = 1000
                            while chunk_start <= current_block:
                                chunk_end = min(chunk_start + BATCH_SIZE - 1, current_block)
                                transfers = await service.get_erc20_deposits(
                                    address,
                                    token_info['address'],
                                    token_info['decimals'],
                                    chunk_start,
                                    chunk_end
                                )
                                for transfer in transfers:
                                    tx_hash = transfer['tx_hash']
                                    token_amount = transfer['amount']

                                    if token_amount < 1:
                                        continue

                                    if await self.db.async_deposit_exists(tx_hash):
                                        continue

                                    amount_usd = token_amount  # stablecoin 1:1 with USD
                                    deposit_id = await self.db.async_add_deposit(
                                        tx_hash=tx_hash,
                                        user_id=user_id,
                                        chain=chain,
                                        token=token_name,
                                        amount=token_amount,
                                        amount_usd=amount_usd,
                                        to_address=address,
                                        block_number=transfer['block_number']
                                    )

                                    if deposit_id:
                                        found_deposit = True
                                        logging.info(f"New token deposit: {token_amount} {token_name} on {chain} for user {telegram_id} (tx: {tx_hash})")
                                        required_confs = CONFIRMATIONS.get(chain, 10)
                                        await self.db.async_update_deposit_status(tx_hash, 'confirmed', confirmations=required_confs)

                                        if telegram_id in user_wallets:
                                            credit_wallet_crypto(telegram_id, token_amount, token_name)
                                            if telegram_id in user_stats:
                                                user_stats[telegram_id]["unwagered_deposit"] = (
                                                    user_stats[telegram_id].get("unwagered_deposit", 0.0) + amount_usd
                                                )

                                            # Referral deposit commission (0.5%)
                                            if telegram_id in user_stats:
                                                ref_data = user_stats[telegram_id].get('referral', {})
                                                referrer_id = ref_data.get('referrer_id')
                                                if referrer_id and referrer_id in user_stats:
                                                    commission = token_amount * 0.005
                                                    ref_dict = user_stats[referrer_id].setdefault('referral', {})
                                                    comm_dict = ref_dict.setdefault('commissions', {})
                                                    comm_dict[token_name] = comm_dict.get(token_name, 0.0) + commission
                                                    save_user_data(referrer_id)
                                                    logging.info(f"Credited {commission} {token_name} deposit commission to referrer {referrer_id}")

                                            save_user_data(telegram_id)
                                            logging.info(f"Credited {token_amount} {token_name} to user {telegram_id}")

                                        if bot:
                                            try:
                                                await bot.send_message(
                                                    chat_id=telegram_id,
                                                    text=(
                                                        f"{pe('win')} <b>Deposit Received!</b>\n\n"
                                                        f"{pe('check')} <b>{token_amount:.2f} {token_name}</b> (${amount_usd:.2f}) "
                                                        f"detected on {chain} and credited to your balance!"
                                                    ),
                                                    parse_mode=ParseMode.HTML
                                                )
                                            except Exception as notify_err:
                                                logging.warning(f"Could not notify user {telegram_id}: {notify_err}")

                                chunk_start = chunk_end + 1
                            self.last_scanned_blocks[track_key] = current_block

                    else:
                        # Non-EVM chains (TRON, SOLANA) or fallback: use balance delta
                        if chain == 'SOLANA':
                            token_balance = await service.get_token_balance(address, token_info['mint'])
                        else:
                            token_balance = await service.get_token_balance(
                                address,
                                token_info['address'],
                                token_info['decimals']
                            )

                        recorded_token_unswept = await self.db.async_get_recorded_unswept(
                            user_id, chain, address, token=token_name
                        )

                        new_token_amount = token_balance - recorded_token_unswept
                        if new_token_amount > 1:  # Minimum 1 token
                            tx_hash = f"token_{chain}_{token_name}_{address}_{int(datetime.now().timestamp())}"
                            amount_usd = new_token_amount  # stablecoin 1:1 with USD

                            deposit_id = await self.db.async_add_deposit(
                                tx_hash=tx_hash,
                                user_id=user_id,
                                chain=chain,
                                token=token_name,
                                amount=new_token_amount,
                                amount_usd=amount_usd,
                                to_address=address
                            )

                            if deposit_id:
                                found_deposit = True
                                logging.info(f"New token deposit: {new_token_amount} {token_name} on {chain} for user {telegram_id}")
                                required_confs = CONFIRMATIONS.get(chain, 10)
                                await self.db.async_update_deposit_status(tx_hash, 'confirmed', confirmations=required_confs)

                                if telegram_id in user_wallets:
                                    credit_wallet_crypto(telegram_id, new_token_amount, token_name)
                                    if telegram_id in user_stats:
                                        user_stats[telegram_id]["unwagered_deposit"] = (
                                            user_stats[telegram_id].get("unwagered_deposit", 0.0) + amount_usd
                                        )

                                    # Referral deposit commission (0.5%)
                                    if telegram_id in user_stats:
                                        ref_data = user_stats[telegram_id].get('referral', {})
                                        referrer_id = ref_data.get('referrer_id')
                                        if referrer_id and referrer_id in user_stats:
                                            commission = new_token_amount * 0.005
                                            ref_dict = user_stats[referrer_id].setdefault('referral', {})
                                            comm_dict = ref_dict.setdefault('commissions', {})
                                            comm_dict[token_name] = comm_dict.get(token_name, 0.0) + commission
                                            save_user_data(referrer_id)
                                            logging.info(f"Credited {commission} {token_name} deposit commission to referrer {referrer_id}")

                                    save_user_data(telegram_id)
                                    logging.info(f"Credited {new_token_amount} {token_name} to user {telegram_id}")

                                if bot:
                                    try:
                                        await bot.send_message(
                                            chat_id=telegram_id,
                                            text=(
                                                f"{pe('win')} <b>Deposit Received!</b>\n\n"
                                                f"{pe('check')} <b>{new_token_amount:.2f} {token_name}</b> (${amount_usd:.2f}) "
                                                f"detected on {chain} and credited to your balance!"
                                            ),
                                            parse_mode=ParseMode.HTML
                                        )
                                    except Exception as notify_err:
                                        logging.warning(f"Could not notify user {telegram_id}: {notify_err}")

        except Exception as e:
            logging.error(f"Error scanning {chain} address {address}: {e}")

        return found_deposit

class AutoSweeper:
    """Automatically sweeps confirmed deposits to master wallet"""

    def __init__(self, db: DepositDatabase):
        self.db = db
        self.wallet_manager = HDWalletManager()
        self.services = {}

        # Initialize services
        for chain in ['ETH', 'BNB', 'BASE']:
            try:
                self.services[chain] = EvmService(chain)
            except Exception as e:
                logging.error(f"Error initializing {chain} service: {e}")

        try:
            self.services['TRON'] = TronService()
        except:
            pass

        try:
            self.services['SOLANA'] = SolanaService()
        except:
            pass

        try:
            self.services['TON'] = TonService()
        except:
            pass

    async def process_pending_sweeps(self):
        """Process all confirmed deposits that need sweeping (fully async via aiosqlite)."""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                cursor = await db.execute('''
                    SELECT d.id, d.tx_hash, d.chain, d.token, d.amount, d.to_address, u.address_index
                    FROM deposits d
                    JOIN user_addresses u ON d.user_id = u.user_id
                    WHERE d.status = 'confirmed' OR (d.status = 'pending' AND d.amount_usd >= ?)
                    ORDER BY d.created_at ASC
                    LIMIT 50
                ''', (MIN_DEPOSIT_USD,))
                deposits = await cursor.fetchall()

            for deposit in deposits:
                dep_id, tx_hash, chain, token, amount, to_address, addr_index = deposit
                try:
                    await self._sweep_deposit(chain, token, to_address, addr_index, tx_hash)
                except Exception as e:
                    logging.error(f"Error sweeping deposit {tx_hash}: {e}")

        except Exception as e:
            logging.error(f"Error in process_pending_sweeps: {e}")

    async def _sweep_deposit(self, chain, token, from_address, address_index, deposit_tx_hash):
        """Sweep individual deposit"""
        try:
            service = self.services.get(chain)
            if not service:
                logging.warning(f"Service not available for {chain}")
                return

            # Get private key
            private_key = self.wallet_manager.derive_private_key(chain, address_index)

            sweep_tx_hash = None

            if token:
                # Token sweep - need to fund gas first
                logging.info(f"Sweeping token {token} on {chain} from {from_address}")

                # Check if address has gas
                native_balance = await service.get_balance(from_address)
                gas_needed = GAS_AMOUNTS.get(chain, 0.001)

                if native_balance < gas_needed:
                    # Fund gas
                    logging.info(f"Funding {gas_needed} {chain} for gas")
                    gas_tx = await service.fund_gas(from_address, gas_needed)

                    if gas_tx:
                        # Atomically raise baseline by gas_needed so BlockMonitor
                        # doesn't credit the incoming gas as a user deposit.
                        await self.db.async_increment_last_native_balance(from_address, chain, gas_needed)
                        # Wait for the gas transaction to be mined before sweeping tokens
                        if hasattr(service, 'wait_for_receipt'):
                            try:
                                await service.wait_for_receipt(gas_tx, timeout=120)
                                logging.info(f"Gas transaction confirmed: {gas_tx}")
                            except Exception as e:
                                logging.error(f"Gas transaction not confirmed within timeout: {e}")
                                return
                        else:
                            await asyncio.sleep(30)  # Fallback for non-EVM chains (conservative; TRON ~3s block, Solana ~0.4s)
                    else:
                        logging.error("Failed to fund gas")
                        return

                # Sweep token
                if chain == 'SOLANA':
                    token_contract = TOKEN_CONTRACTS[chain][token]['mint']
                elif chain in TOKEN_CONTRACTS and token in TOKEN_CONTRACTS[chain]:
                    token_contract = TOKEN_CONTRACTS[chain][token]['address']
                else:
                    logging.error(f"Token contract not found for {token} on {chain}")
                    return

                if chain == 'TRON':
                    sweep_tx_hash = await service.sweep_token(from_address, private_key, token_contract)
                elif chain == 'SOLANA':
                    # Solana SPL token sweep would go here
                    logging.warning("Solana SPL token sweep not fully implemented")
                else:
                    decimals = TOKEN_CONTRACTS[chain][token]['decimals']
                    sweep_tx_hash = await service.sweep_token(from_address, private_key, token_contract, decimals)

                if sweep_tx_hash:
                    await self.db.async_update_deposit_status_swept(
                        deposit_tx_hash,
                        sweep_tx_hash=sweep_tx_hash,
                        swept_at=datetime.now().isoformat()
                    )
                    logging.info(f"Successfully swept token deposit {deposit_tx_hash} - Sweep TX: {sweep_tx_hash}")
                    # Wait for confirmation then lower baseline if balance dropped
                    if hasattr(service, 'wait_for_receipt'):
                        try:
                            await service.wait_for_receipt(sweep_tx_hash, timeout=120)
                        except Exception:
                            pass
                    else:
                        await asyncio.sleep(15)
                    post_sweep_balance = await service.get_balance(from_address)
                    await self.db.async_lower_last_native_balance_if_less(from_address, chain, post_sweep_balance)

            else:
                # Native token sweep
                logging.info(f"Sweeping native {chain} from {from_address}")
                sweep_tx_hash = await service.sweep(from_address, private_key)

                if sweep_tx_hash:
                    await self.db.async_update_deposit_status_swept(
                        deposit_tx_hash,
                        sweep_tx_hash=sweep_tx_hash,
                        swept_at=datetime.now().isoformat()
                    )
                    logging.info(f"Successfully swept native deposit {deposit_tx_hash} - Sweep TX: {sweep_tx_hash}")
                    # Wait for confirmation then atomically lower baseline if post-sweep < current
                    if hasattr(service, 'wait_for_receipt'):
                        try:
                            await service.wait_for_receipt(sweep_tx_hash, timeout=120)
                        except Exception:
                            pass
                    else:
                        await asyncio.sleep(15)
                    post_sweep_balance = await service.get_balance(from_address)
                    await self.db.async_lower_last_native_balance_if_less(from_address, chain, post_sweep_balance)

        except Exception as e:
            logging.error(f"Error in _sweep_deposit: {e}")

global_deposit_db = DepositDatabase()

def check_banned(func):
    """
    Decorator to check if a user is banned before allowing any interaction.
    Blocks both permanently banned users and temp banned users from ALL actions.
    OPTIMIZED: O(1) set lookup instead of rebuilding set() on every call.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return await func(update, context, *args, **kwargs)
        if user.id in _banned_set:
            if update.message:
                await update.message.reply_text("You have been banned from using this bot.", parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer("You have been banned.", show_alert=True)
            return
        if user.id in _tempbanned_set:
            if update.message:
                await update.message.reply_text("You are temporarily banned.", parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer("You are temporarily banned.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

def check_maintenance(func):
    """OPTIMIZED: Reduced lookups and simplified logic."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not bot_settings.get("maintenance_mode", False):
            # Fast path: maintenance off, skip all checks
            return await func(update, context, *args, **kwargs)

        if not user:
            return await func(update, context, *args, **kwargs)

        if is_admin(user.id):
            return await func(update, context, *args, **kwargs)

        # Maintenance mode is ON and user is not admin
        # Allow ongoing game interactions.
        # PERFORMANCE: Use the O(1) per-user active-games index instead of
        # iterating all game_sessions — a full scan was O(N) in games which
        # becomes painful once there are thousands of live/stale sessions.
        if update.message and update.message.dice:
            active_pvb_game_id = context.chat_data.get(f"active_pvb_game_{user.id}")
            if active_pvb_game_id and active_pvb_game_id in game_sessions:
                return await func(update, context, *args, **kwargs)

            chat_id = update.effective_chat.id
            for match_id in list(_get_user_active_game_ids(user.id)):
                match_data = game_sessions.get(match_id)
                if (match_data and match_data.get("chat_id") == chat_id
                        and match_data.get("status") == 'active'):
                    return await func(update, context, *args, **kwargs)

        # Block new commands/interactions
        if update.message:
            await update.message.reply_text(f"{pe('tools')} <b>Bot Under Maintenance</b> 🛠️\n\nThe bot is currently undergoing scheduled maintenance.", parse_mode=ParseMode.HTML)
        elif update.callback_query:
            await update.callback_query.answer(f"{pe('tools')} Bot Under Maintenance", show_alert=True)
        return
    return wrapper

OXAPAY_ASK_AMOUNT = "oxapay_ask_amount"

OXAPAY_ASK_CURRENCY = "oxapay_ask_currency"

async def start_oxapay_webhook_server(application=None):
    """Start the aiohttp web server that receives OxaPay payment callbacks.

    Parameters
    ----------
    application : telegram.ext.Application, optional
        The running Telegram Application whose ``bot`` attribute is used to
        send deposit-confirmation messages to users.
    """
    try:
        global _oxapay_bot_ref

        if not OXAPAY_MERCHANT_KEY or not OXAPAY_WEBHOOK_HOST:
            logging.info(
                "OxaPay webhook server not started "
                "(OXAPAY_MERCHANT_KEY or OXAPAY_WEBHOOK_HOST not set)."
            )
            return

        logging.info("Starting OxaPay webhook server setup...")
        # Store bot reference so the webhook handler can send Telegram messages.
        if application is not None:
            _oxapay_bot_ref = application.bot

        app_web = aiohttp.web.Application()
        app_web.router.add_post("/oxapay_webhook", oxapay_webhook_handler)
        logging.info("Setting up OxaPay webhook runner...")
        runner = aiohttp.web.AppRunner(app_web)
        await runner.setup()
        logging.info("Starting OxaPay webhook site on port %d...", OXAPAY_WEBHOOK_PORT)
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", OXAPAY_WEBHOOK_PORT)
        await site.start()
        logging.info(f"OxaPay webhook server listening on 0.0.0.0:{OXAPAY_WEBHOOK_PORT}")
    except Exception as e:
        logging.error(f"Failed to start OxaPay webhook server: {e}", exc_info=True)

import math  # For math.isfinite in bet validation

def _plinko_cleanup_rate_limits():
    """Periodic cleanup of expired rate limit entries.
    Call this every 30 seconds to prevent memory leaks."""
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - 60

    # Clean rate limit windows
    stale_users = [uid for uid, ts_list in _plinko_rate_limits.items()
                   if not ts_list or ts_list[-1] < cutoff]
    for uid in stale_users:
        del _plinko_rate_limits[uid]

    # Clean last bet time cache (entries older than 5 minutes)
    five_min_ago = now - 300
    stale_cooldowns = [uid for uid, t in _plinko_last_bet_time.items() if t < five_min_ago]
    for uid in stale_cooldowns:
        del _plinko_last_bet_time[uid]

_plinko_html_cache: str | None = None

_plinko_html_cache_time: float = 0

_plinko_html_cache_etag: str = ''

def _get_plinko_web_url() -> str | None:
    """Get the configured Plinko web dashboard URL.
    Uses PLINKO_WEB_URL if set, otherwise falls back to OXAPAY_WEBHOOK_HOST construction."""
    if PLINKO_WEB_URL:
        url = PLINKO_WEB_URL.rstrip('/')
        return f"{url}/plinko"
    if OXAPAY_WEBHOOK_HOST:
        host = OXAPAY_WEBHOOK_HOST.rstrip('/')
        return f"{host}:{PLINKO_WEB_PORT}/plinko"
    return None

_plinko_server_runner = None

_chicken_road_server_runner = None

_plinko_server_running = False

_chicken_road_server_running = False

_PLINKO_CONCURRENCY_LIMIT = 2000  # Max concurrent requests for Plinko (increased for 2k+ users)

_CHICKEN_ROAD_CONCURRENCY_LIMIT = 2000  # Max concurrent requests for Chicken Road (increased for 2k+ users)

_plinko_semaphore = None

_chicken_road_semaphore = None

_plinko_user_cache = {}  # {auth_token_hash: (response_json, expiry_timestamp)}

_chicken_road_user_cache = {}

_USER_CACHE_TTL = 2  # 2 seconds - short enough for balance accuracy, long enough to reduce load

_TCP_KEEPALIVE_INTERVAL = 60  # seconds between keepalive probes

_TCP_KEEPALIVE_COUNT = 10  # number of probes before dropping dead connection

_TCP_KEEPALIVE_IDLE = 30  # seconds of idle before sending first probe

async def start_plinko_web_server(application=None):
    """Start the Plinko web dashboard aiohttp server.
    Upgraded for 4k+ concurrent users with:
    - Request concurrency limiting
    - Response caching for /api/user
    - TCP keepalive for connection stability
    - Optimized backlog for high connection rates"""
    global _plinko_server_runner, _plinko_server_running, _plinko_semaphore
    try:
        if not PLINKO_WEB_ENABLED:
            print("DEBUG: Plinko web dashboard disabled.")
            logging.info("Plinko web dashboard disabled.")
            return

        logging.info(
            f"Starting Plinko web server on port {PLINKO_WEB_PORT} "
            f"(high-concurrency mode)..."
        )

        # Initialize semaphore for this server
        _plinko_semaphore = asyncio.Semaphore(_PLINKO_CONCURRENCY_LIMIT)

        plinko_app = aiohttp.web.Application(client_max_size=PLINKO_MAX_REQUEST_BODY_BYTES)

        # CORS and security middleware
        @aiohttp.web.middleware
        async def cors_and_security_middleware(request, handler):
            # Handle CORS preflight
            if request.method == 'OPTIONS':
                resp = aiohttp.web.Response()
            else:
                resp = await handler(request)
            # Telegram WebApp runs in an iframe; needs permissive CORS
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Auth-Token'
            # Security headers
            resp.headers['X-Content-Type-Options'] = 'nosniff'
            resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            return resp

        plinko_app.middlewares.append(cors_and_security_middleware)

        # Add concurrency limiting middleware (must use @middleware decorator)
        @aiohttp.web.middleware
        async def plinko_concurrency_middleware(request, handler):
            async with _plinko_semaphore:
                return await handler(request)

        plinko_app.middlewares.append(plinko_concurrency_middleware)

        # Routes
        plinko_app.router.add_get('/plinko/health', plinko_health_check)
        plinko_app.router.add_get('/plinko', plinko_serve_html)
        plinko_app.router.add_get('/plinko/', plinko_serve_html)
        plinko_app.router.add_get('/plinko/api/user', plinko_api_user)
        plinko_app.router.add_post('/plinko/api/bet', plinko_api_bet)
        plinko_app.router.add_get('/plinko/api/history', plinko_api_history)

        logging.info("Setting up Plinko web runner...")
        _plinko_server_runner = aiohttp.web.AppRunner(
            plinko_app,
            # Optimize for high concurrency
            handle_signals=False,  # Let main bot handle signals
        )
        await _plinko_server_runner.setup()
        logging.info("Starting Plinko web site on port %d...", PLINKO_WEB_PORT)

        # TCP site with keepalive settings for connection stability
        site = aiohttp.web.TCPSite(
            _plinko_server_runner,
            "0.0.0.0",
            PLINKO_WEB_PORT,
            # High backlog for burst connections (4k+ users)
            backlog=4096,
        )
        await site.start()
        _plinko_server_running = True
        logging.info(f"Plinko web dashboard listening on 0.0.0.0:{PLINKO_WEB_PORT} (concurrency limit: {_PLINKO_CONCURRENCY_LIMIT})")
        plinko_url = _get_plinko_web_url()
        if plinko_url:
            logging.info(f"Plinko WebApp URL: {plinko_url}")
        else:
            logging.warning("PLINKO_WEB_URL not configured! Set it in the config section for Telegram WebApp buttons to work.")
    except Exception as e:
        _plinko_server_running = False
        logging.error(f"Failed to start Plinko web server: {e}", exc_info=True)

async def start_plinko_web_server_with_restart(application=None):
    """Start Plinko web server with automatic restart on failure."""
    global _plinko_server_running
    # PERFORMANCE: dropped five blocking open('/tmp/...','w') debug
    # breadcrumbs from the restart loop — they fired every iteration and
    # were just noise, never read operationally.
    restart_count = 0
    max_restarts = 100  # Essentially unlimited restarts
    base_delay = 1  # Start with 1 second delay

    while restart_count < max_restarts and not bot_stopped:
        try:
            if not PLINKO_WEB_ENABLED:
                return

            if restart_count > 0:
                logging.warning(
                    f"Plinko server restart attempt {restart_count} "
                    "(server crashed)"
                )

            await start_plinko_web_server(application)

            if _plinko_server_running:
                # Server started successfully, reset restart counter
                restart_count = 0
                base_delay = 1

                # Wait indefinitely while server runs
                while _plinko_server_running and not bot_stopped:
                    await asyncio.sleep(60)

                    # Verify server is still responding via health check
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f'http://127.0.0.1:{PLINKO_WEB_PORT}/plinko',
                                                  timeout=aiohttp.ClientTimeout(total=3)) as resp:
                                # If we get a response, server is healthy
                                pass
                    except Exception as health_error:
                        # Health check failed - server is likely dead
                        logging.error(f"Plinko health check failed: {health_error}")
                        _plinko_server_running = False
                        break
            else:
                # Server failed to start, wait and retry
                restart_count += 1
                delay = min(base_delay * (2 ** min(restart_count, 5)), 60)  # Exponential backoff, max 60s
                logging.error(f"Plinko server failed to start. Restarting in {delay}s...")
                await asyncio.sleep(delay)

        except Exception as e:
            _plinko_server_running = False
            restart_count += 1
            delay = min(base_delay * (2 ** min(restart_count, 5)), 60)
            logging.error(f"Plinko server crashed (attempt {restart_count}): {e}")
            logging.error(f"Restarting Plinko server in {delay} seconds...")
            await asyncio.sleep(delay)

    if restart_count >= max_restarts:
        logging.critical("Plinko server exceeded maximum restart attempts. Giving up.")

async def plinko_rate_limit_cleanup_task(application):
    """Background task: periodically clean up stale rate limit entries.
    Runs every 30 seconds to prevent memory leaks under high load."""
    while not bot_stopped:
        try:
            await asyncio.sleep(30)
            _plinko_cleanup_rate_limits()
            # Also clean expired user cache entries
            _cleanup_user_cache(_plinko_user_cache)
        except Exception as e:
            logging.error(f"Rate limit cleanup error: {e}")

def _cleanup_user_cache(cache_dict):
    """Remove expired entries from user response cache."""
    now = datetime.now(timezone.utc).timestamp()
    expired_keys = [k for k, (resp, expiry) in cache_dict.items() if now >= expiry]
    for k in expired_keys:
        del cache_dict[k]

def _get_chicken_road_web_url() -> str | None:
    """Return the Chicken Road WebApp URL."""
    if CHICKEN_ROAD_WEB_URL:
        return CHICKEN_ROAD_WEB_URL.rstrip('/') + '/chicken-road'
    if OXAPAY_WEBHOOK_HOST:
        return OXAPAY_WEBHOOK_HOST.rstrip('/') + f':{CHICKEN_ROAD_WEB_PORT}/chicken-road'
    return None

def _chicken_road_cleanup_rate_limits():
    """Periodic cleanup of expired rate-limit state. Called every 30s."""
    now    = datetime.now(timezone.utc).timestamp()
    cutoff = now - 60.0
    stale  = [uid for uid, ts in _chicken_road_rate_limits.items()
              if not ts or ts[-1] < cutoff]
    for uid in stale:
        del _chicken_road_rate_limits[uid]
    five_min = now - 300.0
    stale2   = [uid for uid, t in _chicken_road_last_bet_time.items() if t < five_min]
    for uid in stale2:
        del _chicken_road_last_bet_time[uid]

async def chicken_road_rate_limit_cleanup_task(application):
    """Background task: clean stale rate-limit entries every 30s."""
    while not bot_stopped:
        try:
            await asyncio.sleep(30)
            _chicken_road_cleanup_rate_limits()
            # Also clean expired user cache entries
            _cleanup_user_cache(_chicken_road_user_cache)
        except Exception as e:
            logging.error(f"Chicken Road rate-limit cleanup error: {e}")

_chicken_road_html_cache: str | None = None

_chicken_road_html_cache_time: float = 0

_chicken_road_html_cache_etag: str = ''

async def start_chicken_road_web_server(application=None):
    """Start the Chicken Road web game aiohttp server on port 8087.
    Upgraded for 4k+ concurrent users with:
    - Request concurrency limiting
    - Response caching for /api/user
    - High backlog for burst connections"""
    global _chicken_road_server_runner, _chicken_road_server_running, _chicken_road_semaphore
    print(f"DEBUG: Starting Chicken Road web server setup on port {CHICKEN_ROAD_WEB_PORT}...")
    try:
        if not CHICKEN_ROAD_WEB_ENABLED:
            logging.info("Chicken Road web game disabled.")
            return

        # Initialize semaphore for this server
        _chicken_road_semaphore = asyncio.Semaphore(_CHICKEN_ROAD_CONCURRENCY_LIMIT)

        cr_app = aiohttp.web.Application(client_max_size=CHICKEN_ROAD_MAX_REQUEST_BODY_BYTES)

        @aiohttp.web.middleware
        async def cors_middleware(request, handler):
            if request.method == 'OPTIONS':
                resp = aiohttp.web.Response()
            else:
                resp = await handler(request)
            resp.headers['Access-Control-Allow-Origin']  = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Auth-Token'
            resp.headers['X-Content-Type-Options']       = 'nosniff'
            resp.headers['Referrer-Policy']              = 'strict-origin-when-cross-origin'
            return resp

        cr_app.middlewares.append(cors_middleware)

        # Add concurrency limiting middleware (must use @middleware decorator)
        @aiohttp.web.middleware
        async def cr_concurrency_middleware(request, handler):
            async with _chicken_road_semaphore:
                return await handler(request)

        cr_app.middlewares.append(cr_concurrency_middleware)

        cr_app.router.add_get('/chicken-road/health',          cr_health_check)
        cr_app.router.add_get('/chicken-road',                 cr_serve_html)
        cr_app.router.add_get('/chicken-road/',                cr_serve_html)
        cr_app.router.add_static('/chicken-road/',             os.path.join(BASE_DIR, 'chicken_road_web'), name='chicken_static')
        cr_app.router.add_get('/chicken-road/api/user',        cr_api_user)
        cr_app.router.add_post('/chicken-road/api/bet',        cr_api_bet)
        cr_app.router.add_post('/chicken-road/api/step',       cr_api_step)
        cr_app.router.add_post('/chicken-road/api/cashout',    cr_api_cashout)
        cr_app.router.add_get('/chicken-road/api/history',     cr_api_history)

        _chicken_road_server_runner = aiohttp.web.AppRunner(
            cr_app,
            handle_signals=False,
        )
        await _chicken_road_server_runner.setup()

        # High backlog for burst connections
        site = aiohttp.web.TCPSite(
            _chicken_road_server_runner,
            "0.0.0.0",
            CHICKEN_ROAD_WEB_PORT,
            backlog=4096,
        )
        await site.start()
        _chicken_road_server_running = True
        cr_url = _get_chicken_road_web_url()
        logging.info(f"Chicken Road web game listening on 0.0.0.0:{CHICKEN_ROAD_WEB_PORT} (concurrency limit: {_CHICKEN_ROAD_CONCURRENCY_LIMIT})")
        if cr_url:
            logging.info(f"Chicken Road WebApp URL: {cr_url}")
    except Exception as e:
        _chicken_road_server_running = False
        logging.error(f"Failed to start Chicken Road web server: {e}", exc_info=True)

async def start_chicken_road_web_server_with_restart(application=None):
    """Start Chicken Road web server with automatic restart on failure."""
    global _chicken_road_server_running
    restart_count = 0
    max_restarts = 100  # Essentially unlimited restarts
    base_delay = 1  # Start with 1 second delay

    while restart_count < max_restarts and not bot_stopped:
        try:
            if not CHICKEN_ROAD_WEB_ENABLED:
                return

            # If server was running but crashed, log the restart
            if restart_count > 0:
                logging.warning(f"Chicken Road server restart attempt {restart_count} (server crashed)")

            await start_chicken_road_web_server(application)

            if _chicken_road_server_running:
                # Server started successfully, reset restart counter
                restart_count = 0
                base_delay = 1

                # Wait indefinitely while server runs
                while _chicken_road_server_running and not bot_stopped:
                    await asyncio.sleep(60)

                    # Verify server is still responding via health check
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f'http://127.0.0.1:{CHICKEN_ROAD_WEB_PORT}/chicken-road',
                                                  timeout=aiohttp.ClientTimeout(total=3)) as resp:
                                # If we get a response, server is healthy
                                pass
                    except Exception as health_error:
                        # Health check failed - server is likely dead
                        logging.error(f"Chicken Road health check failed: {health_error}")
                        _chicken_road_server_running = False
                        break
            else:
                # Server failed to start, wait and retry
                restart_count += 1
                delay = min(base_delay * (2 ** min(restart_count, 5)), 60)  # Exponential backoff, max 60s
                logging.error(f"Chicken Road server failed to start. Restarting in {delay}s...")
                await asyncio.sleep(delay)

        except Exception as e:
            _chicken_road_server_running = False
            restart_count += 1
            delay = min(base_delay * (2 ** min(restart_count, 5)), 60)
            logging.error(f"Chicken Road server crashed (attempt {restart_count}): {e}")
            logging.error(f"Restarting Chicken Road server in {delay} seconds...")
            await asyncio.sleep(delay)

    if restart_count >= max_restarts:
        logging.critical("Chicken Road server exceeded maximum restart attempts. Giving up.")

async def active_scans_monitor_task(application):
    """Background task: every 15 s scan addresses registered via 'Check Status' button.
    When a deposit is found, notify the user via DM and remove them from the scan list."""
    db = global_deposit_db
    monitor = BlockMonitor(db)

    while not bot_stopped:
        try:
            now = datetime.now()
            expired_keys = [k for k, exp in list(active_manual_scans.items()) if now >= exp]
            for key in expired_keys:
                active_manual_scans.pop(key, None)

            for (telegram_id, chain), expiry in list(active_manual_scans.items()):
                try:
                    user_data = await db.async_get_or_create_user(telegram_id)
                    address = user_data.get(f"{chain.lower()}_address")
                    if not address:
                        continue
                    found = await monitor.scan_address(
                        chain, address, user_data['user_id'], telegram_id,
                        bot=application.bot
                    )
                    if found:
                        active_manual_scans.pop((telegram_id, chain), None)
                except Exception as scan_err:
                    logging.error(f"active_scans_monitor_task scan error for {telegram_id}/{chain}: {scan_err}")

            await asyncio.sleep(15)
        except Exception as e:
            logging.error(f"Error in active_scans_monitor_task: {e}")
            await asyncio.sleep(15)

async def sweep_deposits_task(application):
    """Background task to sweep deposits"""
    db = global_deposit_db
    sweeper = AutoSweeper(db)

    while not bot_stopped:
        try:
            await sweeper.process_pending_sweeps()
            await asyncio.sleep(SWEEP_INTERVAL)
        except Exception as e:
            logging.error(f"Error in auto sweeper: {e}")
            await asyncio.sleep(SWEEP_INTERVAL)

async def monitor_raffles_task(application):
    """Background task to monitor and execute raffles"""
    while not bot_stopped:
        try:
            now = datetime.now(timezone.utc)

            # Check each active raffle
            for raffle_id, raffle in list(active_raffles.items()):
                end_time = datetime.fromisoformat(raffle['end_time'].replace('Z', '+00:00'))

                # Check if raffle has ended
                if now >= end_time:
                    logging.info(f"Processing raffle {raffle_id}")

                    # Get all participants with tickets
                    participants = raffle['tickets']
                    if not participants or sum(participants.values()) == 0:
                        # No participants, refund creator
                        creator_id = raffle['creator']
                        prize = raffle['prize_usd']
                        if creator_id in user_wallets:
                            credit_wallet(creator_id, prize)
                            save_user_data(creator_id)
                            try:
                                await application.bot.send_message(
                                    chat_id=creator_id,
                                    text=f"{pe('casino')} Raffle <code>{raffle_id}</code> ended with no participants. Prize ${prize:.2f} refunded.",
                                    parse_mode=ParseMode.HTML
                                )
                            except:
                                pass

                        # Move to completed
                        completed_raffles.append({**raffle, 'winners': [], 'ended_at': str(now)})
                        del active_raffles[raffle_id]
                        save_bot_state()
                        continue

                    # Create ticket pool (each ticket is one entry)
                    ticket_pool = []
                    for user_id, ticket_count in participants.items():
                        ticket_pool.extend([user_id] * ticket_count)

                    # Select winners
                    num_winners = min(raffle['total_winners'], len(set(ticket_pool)))  # Can't have more winners than unique participants
                    winners = []
                    winner_set = set()

                    # Use random.sample to pick unique winners
                    while len(winners) < num_winners and ticket_pool:
                        picked = _secure_choice(ticket_pool)
                        if picked not in winner_set:
                            winners.append(picked)
                            winner_set.add(picked)
                        # Remove all tickets of this user to ensure uniqueness
                        ticket_pool = [t for t in ticket_pool if t != picked]

                    # Distribute prizes equally
                    prize_per_winner = raffle['prize_usd'] / len(winners) if winners else 0

                    for winner_id in winners:
                        if winner_id in user_wallets:
                            # Convert to winner's active currency
                            active_currency = get_active_currency(winner_id)
                            credit_wallet(winner_id, prize_per_winner, active_currency)
                            save_user_data(winner_id)

                            # Notify winner
                            try:
                                await application.bot.send_message(
                                    chat_id=winner_id,
                                    text=(
                                        f"{pe('win')} <b>Congratulations!</b>\n\n"
                                        f"You won ${prize_per_winner:.2f} in raffle <code>{raffle_id}</code>!\n"
                                        f"Prize has been credited to your balance."
                                    ),
                                    parse_mode=ParseMode.HTML
                                )
                            except:
                                pass

                    # Notify creator
                    creator_id = raffle['creator']
                    try:
                        await application.bot.send_message(
                            chat_id=creator_id,
                            text=(
                                f"{pe('casino')} <b>Raffle Completed!</b>\n\n"
                                f"Raffle <code>{raffle_id}</code> has ended.\n"
                                f"{pe('trophy')} Winners: {len(winners)}\n"
                                f"{pe('money')} Prize per winner: ${prize_per_winner:.2f}\n"
                                f"🎫 Total tickets: {sum(participants.values())}"
                            ),
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass

                    # Move to completed
                    completed_raffles.append({
                        **raffle,
                        'winners': winners,
                        'prize_per_winner': prize_per_winner,
                        'ended_at': str(now)
                    })
                    del active_raffles[raffle_id]
                    save_bot_state()
                    logging.info(f"Raffle {raffle_id} completed with {len(winners)} winners")

            # Wait 60 seconds before next check
            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"Error in raffle monitoring: {e}")
            logging.error(traceback.format_exc())
            await asyncio.sleep(60)

def load_language_files():
    """Load all language files at startup into the global LANGUAGES dictionary"""
    global LANGUAGES
    for lang_code, filename in LANGUAGE_FILES.items():
        lang_dict = load_language_file(lang_code)
        if lang_dict:
            # Merge with existing LANGUAGES dict (file takes precedence)
            if lang_code in LANGUAGES:
                LANGUAGES[lang_code].update(lang_dict)
            else:
                LANGUAGES[lang_code] = lang_dict
            logging.info(f"Loaded {len(lang_dict)} translations for {lang_code}")
        else:
            logging.warning(f"Failed to load language file for {lang_code}")

def get_text(user_id_or_key, key_or_lang=None, **kwargs):
    """
    Get translated text based on user's language preference.

    Supports two call signatures for backward compatibility:
    1. get_text(user_id, key, **kwargs) - New preferred signature (user_id can be int or None)
    2. get_text(key, lang_code, **kwargs) - Legacy signature (both are strings)

    Args:
        user_id_or_key: Either user_id (int/None) or translation key (str)
        key_or_lang: Either translation key (str) or language code (str), or None
        **kwargs: Format arguments for string formatting

    Returns:
        Formatted translated string with fallback to English
    """
    # Determine which signature is being used based on type
    if isinstance(user_id_or_key, (int, type(None))):
        # New signature: get_text(user_id, key, **kwargs)
        user_id = user_id_or_key
        key = key_or_lang
        # Get language from user_id, using DEFAULT_LANG only if user_id is explicitly None
        if user_id is not None:
            lang_code = get_user_lang(user_id)
        else:
            lang_code = DEFAULT_LANG
    else:
        # Legacy signature: get_text(key, lang_code, **kwargs)
        key = user_id_or_key
        lang_code = key_or_lang if key_or_lang else DEFAULT_LANG

    # Ensure lang_code is valid
    lang_code = lang_code if lang_code in LANGUAGE_FILES else DEFAULT_LANG

    # Try to get text from LANGUAGES dict (which now includes loaded files)
    if lang_code in LANGUAGES and key in LANGUAGES[lang_code]:
        text = LANGUAGES[lang_code][key]
    elif key in LANGUAGES.get(DEFAULT_LANG, {}):
        text = LANGUAGES[DEFAULT_LANG][key]
    else:
        logging.warning(f"Missing translation key: '{key}'")
        return f"Missing translation for '{key}'"

    # Format the text with provided kwargs
    try:
        return text.format(**kwargs)
    except KeyError as e:
        logging.warning(f"Missing format key {e} in text '{key}' for language '{lang_code}'")
        return text

async def safe_edit_message(query, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    """
    Safely edit a message. If the source is a PhotoMessage in DMs, delete it and send new text message.
    In groups, avoid deleting messages to prevent disappearing menus.
    Automatically sets menu ownership if reply_markup is provided.
    """
    try:
        # Try to edit as text message
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    except Exception:
        # edit_message_text failed - likely a photo message
        chat_type = query.message.chat.type
        if chat_type in ["group", "supergroup"]:
            # In groups: try editing caption first to keep the message visible
            try:
                await query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception:
                # If editing caption fails, send a new message as reply
                try:
                    new_message = await query.message.reply_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    # Set ownership on the new message
                    if reply_markup is not None and hasattr(query, 'from_user'):
                        set_menu_owner(new_message, query.from_user.id)
                    return
                except Exception:
                    pass
        else:
            # In DMs: delete the photo message and send a new text-only message
            # This makes the picture "disappear" when navigating via inline buttons
            try:
                await query.message.delete()
            except Exception:
                pass
            new_message = await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            # Set ownership on the new message
            if reply_markup is not None and hasattr(query, 'from_user'):
                set_menu_owner(new_message, query.from_user.id)
            return

    # Automatically set menu ownership when there's a keyboard
    if reply_markup is not None and hasattr(query, 'from_user'):
        set_menu_owner(query.message, query.from_user.id)

(SELECT_BOMBS, SELECT_BET_AMOUNT, SELECT_TARGET_SCORE, ASK_AI_PROMPT, CHOOSE_AI_MODEL,
 ADMIN_SET_BALANCE_USER, ADMIN_SET_BALANCE_AMOUNT, ADMIN_SET_DAILY_BONUS, ADMIN_SEARCH_USER,
 ADMIN_BROADCAST_MESSAGE, ADMIN_SET_HOUSE_BALANCE, ADMIN_LIMITS_CHOOSE_TYPE,
 ADMIN_LIMITS_CHOOSE_GAME, ADMIN_LIMITS_SET_AMOUNT,
 SETTINGS_RECOVERY_PIN, RECOVER_ASK_TOKEN, RECOVER_ASK_PIN,
 ADMIN_GIFT_CODE_AMOUNT, ADMIN_GIFT_CODE_CLAIMS, ADMIN_GIFT_CODE_WAGER, SETTINGS_WITHDRAWAL_ADDRESS, SETTINGS_WITHDRAWAL_ADDRESS_CHANGE,
 WITHDRAWAL_AMOUNT, WITHDRAWAL_APPROVAL_TXID, TOWER_BET_AMOUNT, PF_CHANGE_CLIENT_SEED_INPUT,
 PF_VERIFY_INPUT_SERVER_SEED, PF_VERIFY_INPUT_CLIENT_SEED, PF_VERIFY_INPUT_NONCE, PF_VERIFY_INPUT_PARAM,
 ROULETTE_BET_AMOUNT, SELECT_WHO_ROLLS_FIRST,
 RAFFLE_PRIZE_AMOUNT, RAFFLE_TICKET_COST, RAFFLE_DURATION, RAFFLE_NUM_WINNERS) = range(36)

ROULETTE_CONFIG = {
    "single_number": {"multiplier": 35, "count": 1},
    "red": {"multiplier": 1.96, "numbers": [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
    "black": {"multiplier": 1.96, "numbers": [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]},
    "even": {"multiplier": 1.96, "numbers": [2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36]},
    "odd": {"multiplier": 1.96, "numbers": [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35]},
    "low": {"multiplier": 1.96, "numbers": list(range(1, 19))},
    "high": {"multiplier": 1.96, "numbers": list(range(19, 37))},
    "column1": {"multiplier": 2.92, "numbers": [1,4,7,10,13,16,19,22,25,28,31,34]},
    "column2": {"multiplier": 2.92, "numbers": [2,5,8,11,14,17,20,23,26,29,32,35]},
    "column3": {"multiplier": 2.92, "numbers": [3,6,9,12,15,18,21,24,27,30,33,36]},
    # Dozen bets (1-12, 13-24, 25-36) - different from column bets!
    "dozen1": {"multiplier": 2.92, "numbers": list(range(1, 13))},   # 1-12
    "dozen2": {"multiplier": 2.92, "numbers": list(range(13, 25))},  # 13-24
    "dozen3": {"multiplier": 2.92, "numbers": list(range(25, 37))},  # 25-36
}

TOWER_MULTIPLIERS = {
    'easy': {  # 4 tiles per floor, 25% risk (1 snake out of 4)
        0: 0.90,  # Floor 0 - can cash out immediately
        1: 1.27, 2: 1.69, 3: 2.25, 4: 3.01, 5: 4.01, 6: 5.34, 7: 7.12, 8: 9.50, 9: 12.66
    },
    'medium': {  # 3 tiles per floor, 33% risk (1 snake out of 3)
        0: 0.90,
        1: 1.43, 2: 2.14, 3: 3.21, 4: 4.81, 5: 7.22, 6: 10.83, 7: 16.24, 8: 24.36, 9: 36.54
    },
    'hard': {  # 2 tiles per floor, 50% risk (1 snake out of 2)
        0: 0.90,
        1: 1.90, 2: 3.80, 3: 7.60, 4: 15.21, 5: 30.42, 6: 60.84, 7: 121.68, 8: 243.35, 9: 486.71
    }
}

TOWER_DIFFICULTY_CONFIG = {
    'easy': {'tiles': 4, 'risk': '25%', 'name': 'Easy'},
    'medium': {'tiles': 3, 'risk': '33%', 'name': 'Medium'},
    'hard': {'tiles': 2, 'risk': '50%', 'name': 'Hard'}
}

CARD_VALUES = {
    'A': [1, 11], '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10
}

SUITS = ['♠', '♥', '♦', '♣']

RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

MINES_MULT_TABLE = {
    # 1 Bomb
    1: {1: 1.01, 2: 1.06, 3: 1.1, 4: 1.16, 5: 1.22, 6: 1.27, 7: 1.34, 8: 1.43, 9: 1.52, 10: 1.62, 11: 1.73, 12: 1.86, 13: 2.02, 14: 2.21, 15: 2.42, 16: 2.69, 17: 3.03, 18: 3.47, 19: 4.04, 20: 4.85, 21: 6.07, 22: 8.08, 23: 12.12, 24: 24.25},
    # 2 Bombs
    2: {1: 1.06, 2: 1.15, 3: 1.26, 4: 1.38, 5: 1.53, 6: 1.71, 7: 1.9, 8: 2.14, 9: 2.42, 10: 2.77, 11: 3.19, 12: 3.73, 13: 4.41, 14: 5.29, 15: 6.47, 16: 8.08, 17: 10.4, 18: 13.86, 19: 19.4, 20: 29.11, 21: 48.51, 22: 97.02, 23: 291.06},
    # 3 Bombs
    3: {1: 1.1, 2: 1.26, 3: 1.45, 4: 1.68, 5: 1.96, 6: 2.3, 7: 2.73, 8: 3.28, 9: 3.99, 10: 4.9, 11: 6.13, 12: 7.8, 13: 10.14, 14: 13.52, 15: 18.59, 16: 26.57, 17: 39.85, 18: 63.76, 19: 111.57, 20: 223.15, 21: 584.33, 22: 2231.46},
    # 4 Bombs
    4: {1: 1.16, 2: 1.38, 3: 1.68, 4: 2.05, 5: 2.53, 6: 3.17, 7: 4.01, 8: 5.15, 9: 6.74, 10: 8.99, 11: 12.26, 12: 17.17, 13: 24.79, 14: 37.19, 15: 58.45, 16: 97.4, 17: 175.33, 18: 350.65, 19: 818.2, 20: 2454.61, 21: 12273.03},
    # 5 Bombs
    5: {1: 1.22, 2: 1.53, 3: 1.96, 4: 2.53, 5: 3.32, 6: 4.43, 7: 6.02, 8: 8.33, 9: 11.8, 10: 17.17, 11: 25.74, 12: 40.05, 13: 65.08, 14: 111.57, 15: 204.55, 16: 409.1, 17: 920.47, 18: 2454.61, 19: 8591.12, 20: 51546.73},
    # 6 Bombs
    6: {1: 1.27, 2: 1.71, 3: 2.3, 4: 3.17, 5: 4.43, 6: 6.33, 7: 9.25, 8: 13.89, 9: 21.45, 10: 34.33, 11: 57.21, 12: 100.13, 13: 185.95, 14: 371.91, 15: 818.2, 16: 2045.5, 17: 6136.52, 18: 24546.06, 19: 171822.42},
    # 7 Bombs
    7: {1: 1.34, 2: 1.9, 3: 2.73, 4: 4.01, 5: 6.02, 6: 9.25, 7: 14.65, 8: 23.98, 9: 40.77, 10: 72.47, 11: 135.89, 12: 271.78, 13: 588.85, 14: 1413.26, 15: 3886.45, 16: 12954.86, 17: 58296.89, 18: 466375.14},
    # 8 Bombs
    8: {1: 1.43, 2: 2.14, 3: 3.28, 4: 5.15, 5: 8.33, 6: 13.89, 7: 23.98, 8: 43.17, 9: 81.54, 10: 163.07, 11: 349.43, 12: 815.34, 13: 2119.89, 14: 6359.66, 15: 23318.76, 16: 116593.79, 17: 1049344.06},
    # 9 Bombs
    9: {1: 1.52, 2: 2.42, 3: 3.99, 4: 6.74, 5: 11.8, 6: 21.45, 7: 40.77, 8: 81.54, 9: 173.26, 10: 396.02, 11: 990.05, 12: 2772.16, 13: 9009.52, 14: 36038.08, 15: 198209.43, 16: 1982094.34},
    # 10 Bombs
    10: {1: 1.62, 2: 2.77, 3: 4.9, 4: 8.99, 5: 17.17, 6: 34.33, 7: 72.47, 8: 163.07, 9: 396.02, 10: 1056.06, 11: 3168.18, 12: 11088.64, 13: 48315.37, 14: 288304.63, 15: 3171350.95},
    # 11 Bombs
    11: {1: 1.73, 2: 3.19, 3: 6.13, 4: 12.26, 5: 25.74, 6: 57.21, 7: 135.89, 8: 349.43, 9: 990.05, 10: 3168.18, 11: 11880.69, 12: 55443.2, 13: 360380.79, 14: 4324569.48},
    # 12 Bombs
    12: {1: 1.86, 2: 3.73, 3: 7.8, 4: 17.17, 5: 40.05, 6: 100.13, 7: 271.78, 8: 815.34, 9: 2772.16, 10: 11088.64, 11: 55443.2, 12: 388102.39, 13: 5045331.06},
    # 13 Bombs
    13: {1: 2.02, 2: 4.41, 3: 10.14, 4: 24.79, 5: 65.08, 6: 185.95, 7: 588.85, 8: 2119.89, 9: 9009.52, 10: 48315.37, 11: 360380.79, 12: 5045331.06},
    # 14 Bombs
    14: {1: 2.21, 2: 5.29, 3: 13.52, 4: 37.19, 5: 111.57, 6: 371.91, 7: 1413.26, 8: 6359.66, 9: 36038.08, 10: 288304.63, 11: 4324569.48},
    # 15 Bombs
    15: {1: 2.42, 2: 6.47, 3: 18.59, 4: 58.45, 5: 204.55, 6: 818.2, 7: 3886.45, 8: 23318.76, 9: 198209.43, 10: 3171350.95},
    # 16 Bombs
    16: {1: 2.69, 2: 8.08, 3: 26.57, 4: 97.4, 5: 409.1, 6: 2045.5, 7: 12954.86, 8: 116593.79, 9: 1982094.34},
    # 17 Bombs
    17: {1: 3.03, 2: 10.4, 3: 39.85, 4: 175.33, 5: 920.47, 6: 6136.52, 7: 58296.89, 8: 1049344.06},
    # 18 Bombs
    18: {1: 3.47, 2: 13.86, 3: 63.76, 4: 350.65, 5: 2454.61, 6: 24546.06, 7: 466375.14},
    # 19 Bombs
    19: {1: 4.04, 2: 19.4, 3: 111.57, 4: 818.2, 5: 8591.12, 6: 171822.42},
    # 20 Bombs
    20: {1: 4.85, 2: 29.11, 3: 223.15, 4: 2454.61, 5: 51546.73},
    # 21 Bombs
    21: {1: 6.07, 2: 48.51, 3: 557.87, 4: 12273.03},
    # 22 Bombs
    22: {1: 8.08, 2: 97.02, 3: 2231.46},
    # 23 Bombs
    23: {1: 12.12, 2: 291.06},
    # 24 Bombs
    24: {1: 24.25}
}

KENO_PAYOUTS = {
    1: {1: 3.96},
    2: {1: 1.9, 2: 4.5},
    3: {1: 1.0, 2: 3.1, 3: 10.4},
    4: {1: 0.8, 2: 1.8, 3: 5.0, 4: 22.5},
    5: {1: 0.25, 2: 1.4, 3: 4.1, 4: 16.5, 5: 36.0},
    6: {2: 1.0, 3: 3.68, 4: 7.0, 5: 16.5, 6: 40.0},
    7: {2: 0.47, 3: 3.0, 4: 4.5, 5: 14.0, 6: 31.0, 7: 60.0},
    8: {3: 2.2, 4: 4.0, 5: 13.0, 6: 22.0, 7: 55.0, 8: 70.0},
    9: {3: 1.55, 4: 3.0, 5: 8.0, 6: 15.0, 7: 44.0, 8: 60.0, 9: 85.0},
    10: {3: 1.4, 4: 2.25, 5: 4.5, 6: 8.0, 7: 17.0, 8: 50.0, 9: 80.0, 10: 100.0}
}

SINGLE_EMOJI_GAMES = {
    "darts": {
        "emoji": "🎯",
        "name": "Single Dart",
        "dice_type": "🎯",  # Use emoji directly for Telegram API
        "multiplier": 1.15,
        "win_chance": 0.83,  # 83%
        "win_condition": lambda value: value >= 3,  # Dart hits the table (values 3-6)
        "win_description": "Dart hits the table"
    },
    "soccer": {
        "emoji": "⚽",
        "name": "Single Soccer",
        "dice_type": "⚽",  # Use emoji directly for Telegram API
        "multiplier": 1.53,
        "win_chance": 0.60,  # 60%
        "win_condition": lambda value: value in [3, 4, 5],  # Goal scored
        "win_description": "Goal scored"
    },
    "basket": {
        "emoji": "🏀",
        "name": "Single Basket",
        "dice_type": "🏀",  # Use emoji directly for Telegram API
        "multiplier": 2.25,
        "win_chance": 0.40,  # 40%
        "win_condition": lambda value: value in [4, 5],  # Ball goes in basket
        "win_description": "Ball goes in"
    },
    "bowling": {
        "emoji": "🎳",
        "name": "Single Bowling",
        "dice_type": "🎳",  # Use emoji directly for Telegram API
        "multiplier": 5.00,
        "win_chance": 0.16,  # 16%
        "win_condition": lambda value: value == 6,  # Strike
        "win_description": "Strike!"
    },
    "slot": {
        "emoji": "🎰",
        "name": "Slot Machine",
        "dice_type": "🎰",  # Use emoji directly for Telegram API
        "multiplier": 14.5,
        "win_chance": 0.0625,  # 6.25%
        "win_condition": lambda value: value in [1, 22, 43, 64],  # All same symbols (bar, grapes, lemon, seven)
        "win_description": "Same symbols"
    }
}

ROULETTE_STICKERS = [
    "CAACAgQAAyEFAASrImQNAAIBvWiLZDne0b_gDav_cu9Zoz_Wn8QAA9QYAAJJoYBRv9LvNhOfZtw2BA", # 0
    "CAACAgQAAyEFAASrImQNAAIBxWiLZNEh0p7950vmRhKNC3S3ZU25AAKoFgAC9OuBUThYKjFsHNUINgQ", # 1
    "CAACAgQAAyEFAASrImQNAAIBx2iLZOqAubPVdNGdZzvcnsXjTpqpAALVFgAChvR5UXXNtwbTRSMzNgQ", # 2
    "CAACAgQAAyEFAASrImQNAAIBzWiLZQ6zjkGiwJm-7gMR-5pTaDl7AAJJGAACzviBUTIdC1OxHKQaNgQ", # 3
    "CAACAgQAAyEFAASrImQNAAIBz2iLZSVhamntTktG1qeRTcyAamngAAJ8GAACDciAUYSN0sp7C2LnNgQ", # 4
    "CAACAgQAAyEFAASrImQNAAIB0WiLZT6zKhE_zIZeIN7b3S6tUzh8AALKFgACW3KBUQIpefveRTIKNgQ", # 5
    "CAACAgQAAyEFAASrImQNAAIB02iLZVAeRDcVkPbHf67K-6P9hMSkAALLGgACC62BUbKIJ7iU0rb4NgQ", # 6
    "CAACAgQAAyEFAASrImQNAAIB1WiLZWLCIx-z_rMuhRNLgPR1qW54AALVGAAClPyBUSUxwoUHdsn8NgQ", # 7
    "CAACAgQAAyEFAASrImQNAAIB12iLZXTKXalIWjkrGoCaVd1kdLwWAAKAFAACaVaBUUiaHozlFwAB0jYE", # 8
    "CAACAgQAAyEFAASrImQNAAIB2WiLZYebcuzYSQbvfQPnMdLARswWAALgFwAC88p5UUHH5NnJwBYPNgQ", # 9
    "CAACAgQAAyEFAASrImQNAAIB22iLZZmLTjEPN3kacYZtInsUCKZtAALyGAACucCAUZ6fXOAfAAEs9zYE", # 10
    "CAACAgQAAyEFAASrImQNAAIB3WiLZb-01H91oXUKEFcGpCv8nAupAALZEwACbN2BURqjRgAB0jLjWDYE", # 11
    "CAACAgQAAyEFAASrImQNAAIB4WiLZdWV8Mm3ERAAAUtDcsbOQB8F4gACVRgAAovngVFUjR-qYgq8LDYE", # 12
    "CAACAgQAAyEFAASrImQNAAIB8miLZi2XoFr2zDBIJmb7FqK_NWeNAAJNHQACZzSAUdecnnT052I6NgQ", # 13
    "CAACAgQAAyEFAASrImQNAAIB9GiLZkNMlJ-I8vVZ0hrPyeKG1IdTAAJDGQACpcN5URDm4Ifd0r06NgQ", # 14
    "CAACAgQAAyEFAASrImQNAAIB92iLZlqc-BO3IIxiXkyXlKi0iZfBAAKtFgACUFaBUf0GoZ1742K-NgQ", # 15
    "CAACAgQAAyEFAASrImQNAAIB-2iLZmnlAfTNlsfSaexM1GASzMAbAAKvGwACRx95Ub2KbQXS25k_NgQ", # 16
    "CAACAgQAAyEFAASrImQNAAICAWiLZoVPqOAoPNEu8ciguHbhPth-AAIuGAACK5eBUdo-jXChdkRhNgQ", # 17
    "CAACAgQAAyEFAASrImQNAAICBGiLZpjAERL_jSk0_Knhenev_rEkAAJjGQACfHt4Uaxk_YBdcErDNgQ", # 18
    "CAACAgQAAyEFAASrImQNAAICBmiLZqsspVHNaTc4ENzdfqcJEPqmAAIpGQACsPCAUfSIqog8-IdgNgQ", # 19
    "CAACAgQAAyEFAASrImQNAAICDGiLZsPmYc3VwL5hWWfQr62cb10_AAJzGgACvs54UZK5KgfIrF_lNgQ", # 20
    "CAACAgQAAyEFAASrImQNAAICDmiLZtWGzKI2zY3wzLprkoAqc-KVAALGFwAC_V2AUXeSG0ZgWd5jNgQ", # 21
    "CAACAgQAAyEFAASrImQNAAICEGiLZuNlaO9D0c85DyutySD1u_qMAAMZAAITwoBRIlMrM9BBD0g2BA", # 22
    "CAACAgQAAyEFAASrImQNAAICEmiLZvojsOnJx8YE-yfuFiZmpe6cAAJMGAAC6d2BUXq6dfIzfhljNgQ", # 23
    "CAACAgQAAyEFAASrImQNAAICFGiLZwjZ2PZBmj4YgAKLvUrmAkbNAALhGgACeS-AUdEviXb3bvCcNgQ", # 24
    "CAACAgQAAyEFAASrImQNAAICFmiLZxey5PH6Qm_FuX_ar_n1Qr8DAALmFwACI96AUWwyQ3Omp9HTNgQ", # 25
    "CAACAgQAAyEFAASrImQNAAICGWiLZygMUnBPnLmep_qtebbW-ucoAALNIAACfXmBUb6hDihoktivNgQ", # 26
    "CAACAgQAAyEFAASrImQNAAICHGiLZziBU-1FLh5G2ZwRDFoJXShpAAKgFwACMrSBUWqhExYnRXYCNgQ", # 27
    "CAACAgQAAyEFAASrImQNAAICHmiLZ0a5rK8mKDySuCZ5xWhG6R3XAALzFQACNO2BUVsOM4juGOTINgQ", # 28
    "CAACAgQAAyEFAASrImQNAAICIGiLZ1pVZYUGwoBvfOBIUySGC1_3AAJ6FwACAvZ4UXK88kRPGqWWNgQ", # 29
    "CAACAgQAAyEFAASrImQNAAICImiLZ2zFmnOl2hUGfKqGwmrWVFPAAAKsFQACoyyBUSIq6OlCBV8kNgQ", # 30
    "CAACAgQAAyEFAASrImQNAAICJGiLZ352bXF_C2aVFEgnO-dlGOJtAAIOGwACtbqAUQ1y_oj3ur3ENgQ", # 31
    "CAACAgQAAyEFAASrImQNAAICJmiLZ4u_-YlnmI26z9JRKtnREL1cAAJbFwACyad5UYWo5iH3DzX9NgQ", # 32
    "CAACAgQAAyEFAASHyrY2AAIIZGiLRIkLwf5ktSB3VkFL8pReOa9BAAKMGQACjcl4URhc62AjMUuNNgQ", # 33
    "CAACAgQAAyEFAASrImQNAAICKmiLZ-hPWbW7WDMTkhBmtZYy66oNAAJYFgAC-feBUSUjonJS-hFjNgQ", # 34
    "CAACAgQAAyEFAASrImQNAAICLGiLZ_PGUGYeKbdSWBr0uvv5TAirAAKSFgACwpOAUcdyb2uPc8PINgQ", # 35
    "CAACAgQAAyEFAASrImQNAAICLmiLaAABmtHjXzRZDz5Zy3dT5v8v0wACrBcAAtbQgVFt8Uw1gyn4MDYE", # 36
]

def _secure_choice(seq):
    """Cryptographically secure random choice from a sequence.
    Replaces random.choice() with secrets-based implementation."""
    if not seq:
        raise ValueError("Cannot choose from empty sequence")
    idx = secrets.randbelow(len(seq))
    return seq[idx]

def generate_server_seed():
    """Generate a cryptographically secure 64-character server seed."""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))

def generate_client_seed():
    """Generate a client seed - used for user's stored client seed (16 chars).
    Uses cryptographically secure random generation."""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

def generate_unique_id(prefix='G'):
    timestamp = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"{prefix}-{timestamp}-{random_part}"

def generate_unique_referral_code():
    """Generate a unique 6-character alphanumeric referral code.
    Returns a code that doesn't already exist in referral_codes dictionary."""
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        if code not in referral_codes:
            return code

emoji_send_timestamps = {}  # Track last emoji send time per chat

def normalize_username(username):
    if not username:
        return None
    username = username.lower()
    if not username.startswith("@"):
        username = "@" + username
    return username

def load_all_user_data():
    global user_wallets, username_to_userid, user_stats
    try:
        import orjson as _json_lib
        _loads = _json_lib.loads
        _open_mode = "rb"
    except ImportError:
        _loads = json.loads
        _open_mode = "r"

    for fname in os.listdir(DATA_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, fname), _open_mode) as f:
                data = _loads(f.read())
            user_id = int(fname.split(".")[0])
            # Migration: convert float wallet to dict
            raw_wallet = data.get("wallet", 0.0)
            if isinstance(raw_wallet, (int, float)):
                user_wallets[user_id] = {"USDT": float(raw_wallet)}
            elif isinstance(raw_wallet, dict):
                # Validate dict values are numeric
                clean_wallet = {}
                for k, v in raw_wallet.items():
                    try:
                        clean_wallet[k] = float(v)
                    except (TypeError, ValueError):
                        logging.warning(f"Invalid wallet value for user {user_id}, coin {k}: {v}")
                user_wallets[user_id] = clean_wallet if clean_wallet else {"USDT": 0.0}
            else:
                user_wallets[user_id] = {"USDT": 0.0}
            # Migrate active_currency to user_stats
            if "active_currency" not in data:
                data["active_currency"] = "USDT"
            username = data.get("userinfo", {}).get("username")
            if username:
                username_to_userid[normalize_username(username)] = user_id
            user_stats[user_id] = data

            # Apply list caps immediately (Fix #9/#10)
            if user_id in user_stats:
                st = user_stats[user_id]
                bh = st.get("bets", {}).get("history", [])
                if len(bh) > 500:
                    st["bets"]["history"] = bh[-500:]
                    _dirty_users.add(user_id)
                gs = st.get("game_sessions", [])
                if len(gs) > 100:
                    st["game_sessions"] = gs[-100:]
                    _dirty_users.add(user_id)
                for list_key in ("deposits", "withdrawals"):
                    lst = st.get(list_key, [])
                    if len(lst) > 200:
                        st[list_key] = lst[-200:]
                        _dirty_users.add(user_id)
        except (json.JSONDecodeError, ValueError, Exception) as e:
            logging.error(f"Could not load data for {fname}: {e}")

def save_user_data(user_id):
    """
    OPTIMIZED: Non-blocking mark-dirty. Actual write is deferred to background flush task.
    When PostgreSQL is enabled, marks for PostgreSQL flush; otherwise marks for JSON file write.
    Interface is unchanged — no other code needs to be modified.
    """
    if USE_POSTGRES_FOR_ALL and pg_db:
        pg_db._dirty_users.add(user_id)
    else:
        _dirty_users.add(user_id)

async def _flush_dirty_users():
    """Background task: flush dirty users to disk with adaptive interval.
    PERFORMANCE: Under high load (many dirty users), flushes every 3s.
    Under low load, flushes every 10s. This reduces I/O under normal conditions
    while staying responsive under heavy use."""
    while True:
        # Adaptive interval: faster under heavy load
        pending_count = len(_dirty_users)
        if pending_count > 100:
            interval = 2   # Heavy load: flush fast
        elif pending_count > 20:
            interval = 3   # Moderate load
        elif pending_count > 0:
            interval = 5   # Normal load
        else:
            interval = 10  # Idle: check less often

        await asyncio.sleep(interval)
        if not _dirty_users:
            continue
        async with _dirty_lock:
            batch = list(_dirty_users)
            _dirty_users.clear()
        loop = asyncio.get_running_loop()
        # PERFORMANCE: Batch into chunks to avoid overwhelming the executor.
        # Materialise the list once (the previous code rebuilt `list(batch)`
        # on every chunk which was O(n) per iteration — fine at 50 users,
        # wasteful at 5000).
        chunk_size = 50
        for i in range(0, len(batch), chunk_size):
            chunk = batch[i:i + chunk_size]
            tasks = [
                loop.run_in_executor(_save_executor, _sync_write_user, uid)
                for uid in chunk
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        if len(batch) > 10:
            logging.debug(f"Flushed {len(batch)} dirty users to disk")

def _sync_save_bot_state_json():
    state = {
        'username_to_userid': username_to_userid,
        'game_sessions': {k: v for k, v in game_sessions.items()
                          if v.get('status') == 'active'},
        'user_pending_invitations': user_pending_invitations,
        'escrow_deals': escrow_deals,
        'withdrawal_requests': {k: v for k, v in withdrawal_requests.items()
                               if v.get('status') == 'pending'},  # Persist pending withdrawals
        'bot_stopped': bot_stopped,
        'bot_settings': {k: v for k, v in bot_settings.items()
                         if k != 'menu_owners'},  # NEVER persist menu_owners
        'referral_codes': referral_codes,
        'active_raffles': active_raffles,
        'completed_raffles': completed_raffles,
        'leaderboard_data': leaderboard_data,
        'leaderboard_last_update': {
            k: v.isoformat() for k, v in leaderboard_last_update.items()
        },
    }
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, default=str)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logging.error(f"Failed to save bot state JSON: {e}")

_bot_state_dirty: bool = False

_bot_state_extras_dirty: bool = False  # escrow / groups / recovery / gift codes

_bot_state_dirty_lock = asyncio.Lock()

def save_bot_state():
    """Persist non-user-data ("bot state") — called from many admin handlers.

    Now non-blocking: flips a dirty flag and lets ``_flush_bot_state_loop``
    coalesce writes to ``_save_executor``. Worst-case staleness on crash:
    one ``BOT_STATE_FLUSH_INTERVAL`` window. Synchronous shutdown still
    forces an immediate flush via ``save_bot_state_full()``.
    """
    global _bot_state_dirty, _bot_state_extras_dirty
    _bot_state_dirty = True
    _bot_state_extras_dirty = True

BOT_STATE_FLUSH_INTERVAL = 5  # seconds

async def _flush_bot_state_loop():
    """Background loop coalescing ``save_bot_state()`` writes off the event loop."""
    global _bot_state_dirty, _bot_state_extras_dirty
    while True:
        try:
            await asyncio.sleep(BOT_STATE_FLUSH_INTERVAL)
            if not (_bot_state_dirty or _bot_state_extras_dirty):
                continue
            do_state = _bot_state_dirty
            do_extras = _bot_state_extras_dirty
            _bot_state_dirty = False
            _bot_state_extras_dirty = False
            loop = asyncio.get_running_loop()
            try:
                if do_state:
                    await loop.run_in_executor(_save_executor, _sync_save_bot_state_json)
                if do_extras:
                    await loop.run_in_executor(_save_executor, save_all_escrow_deals)
                    await loop.run_in_executor(_save_executor, save_all_group_settings)
                    await loop.run_in_executor(_save_executor, save_all_recovery_data)
                    await loop.run_in_executor(_save_executor, save_all_gift_codes)
            except Exception as e:
                logging.error(f"Bot state flush failed: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"_flush_bot_state_loop error: {e}")

def save_bot_state_full():
    """Full shutdown save — flushes EVERY user file synchronously via thread
    pool, plus all global registries. Only call from the shutdown path."""
    logging.info("Shutdown: saving all user data...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(_sync_write_user, uid) for uid in list(user_stats.keys())]
        concurrent.futures.wait(futures, timeout=60)
    _sync_save_bot_state_json()
    save_all_escrow_deals()
    save_all_group_settings()
    save_all_recovery_data()
    save_all_gift_codes()
    logging.info("Shutdown save complete.")

def load_bot_state():
    """Loads the bot state from PostgreSQL (preferred) or JSON files (fallback)."""
    global user_wallets, username_to_userid, user_stats, game_sessions, user_pending_invitations, escrow_deals, bot_stopped, bot_settings, group_settings, recovery_data, gift_codes, referral_codes, active_raffles, completed_raffles, leaderboard_data, leaderboard_last_update

    # Load from PostgreSQL if enabled
    if USE_POSTGRES_FOR_ALL and pg_db:
        try:
            logging.info("Loading user data from PostgreSQL...")
            # PostgreSQL module handles loading in post_init via async call
            # For sync compatibility, we'll load in post_init instead
            logging.info("PostgreSQL mode: user data will be loaded in post_init")
        except Exception as e:
            logging.error(f"Failed to initialize PostgreSQL loading: {e}")
            logging.info("Falling back to JSON file loading")
            load_all_user_data()
    else:
        # Load individual files first as a fallback
        load_all_user_data()
    load_all_escrow_deals()
    load_all_group_settings() # NEW
    load_all_recovery_data() # NEW
    load_all_gift_codes() # NEW

    # Load persistent OxaPay processed orders to prevent double-credits after restart
    _load_oxapay_processed_orders()

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            # Convert string keys back to int for wallets and migrate floats to dicts
            for k, v in state.get('user_wallets', {}).items():
                uid = int(k)
                if isinstance(v, (int, float)):
                    user_wallets[uid] = {"USDT": float(v)}
                elif isinstance(v, dict):
                    user_wallets[uid] = v
                else:
                    user_wallets[uid] = {"USDT": 0.0}
            username_to_userid.update(state.get('username_to_userid', {}))
            game_sessions.update(state.get('game_sessions', {}))
            user_pending_invitations.update(state.get('user_pending_invitations', {}))
            escrow_deals.update(state.get('escrow_deals', {}))
            # Restore pending withdrawal requests from previous session
            withdrawal_requests.update(state.get('withdrawal_requests', {}))
            # Reset bot_stopped on startup - the bot is starting fresh
            bot_stopped = False
            bot_settings.update(state.get('bot_settings', {})) # NEW
            referral_codes.update(state.get('referral_codes', {})) # NEW: Referral system
            active_raffles.update(state.get('active_raffles', {})) # NEW: Raffle system
            completed_raffles.extend(state.get('completed_raffles', [])) # NEW: Raffle system

            # Restore leaderboard data from saved state
            saved_leaderboard = state.get('leaderboard_data')
            if saved_leaderboard:
                for key in ["all_time", "weekly", "monthly", "highest_wins"]:
                    if key in saved_leaderboard:
                        leaderboard_data[key] = saved_leaderboard[key]
                logging.info("Leaderboard data restored from state file.")

            # Restore leaderboard last update timestamps
            saved_last_update = state.get('leaderboard_last_update')
            if saved_last_update:
                try:
                    leaderboard_last_update["weekly_reset"] = datetime.fromisoformat(saved_last_update.get("weekly_reset", datetime.now(timezone.utc).isoformat()))
                    leaderboard_last_update["monthly_reset"] = datetime.fromisoformat(saved_last_update.get("monthly_reset", datetime.now(timezone.utc).isoformat()))
                except (ValueError, TypeError):
                    logging.warning("Could not parse leaderboard timestamps, using defaults.")
                logging.info("Leaderboard timestamps restored from state file.")

            logging.info("Bot state restored successfully from state file.")
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Could not load bot state from {STATE_FILE}: {e}. Relying on individual files.")
    else:
        logging.info("No state file found. Starting with a fresh state from individual user/escrow files.")

    # CRITICAL FIX: Rebuild all_time leaderboard from user_stats (persisted data)
    # This ensures leaderboard is populated even if buffer was lost on previous shutdown
    logging.info("Rebuilding all_time leaderboard from user_stats...")
    leaderboard_data["all_time"] = []
    for uid, stats in user_stats.items():
        total_wagered = stats.get('bets', {}).get('amount', 0.0)
        if total_wagered > 0:
            username = stats.get('userinfo', {}).get('username', f'User-{uid}')
            username = username.lstrip('@')
            leaderboard_data["all_time"].append((uid, username, total_wagered))
    # Sort by wagered amount descending and keep top 10
    leaderboard_data["all_time"].sort(key=lambda x: x[2], reverse=True)
    leaderboard_data["all_time"] = leaderboard_data["all_time"][:10]
    logging.info(f"All-time leaderboard rebuilt with {len(leaderboard_data['all_time'])} entries")

def load_all_escrow_deals():
    global escrow_deals
    logging.info("Loading all escrow deals from files...")
    for fname in os.listdir(ESCROW_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(ESCROW_DIR, fname), "r") as f:
                    deal = json.load(f)
                    deal_id = deal.get("id")
                    if deal_id:
                        # Only load active deals into memory
                        if deal.get("status") not in ["completed", "cancelled_by_owner", "disputed", "release_failed"]:
                            escrow_deals[deal_id] = deal
            except Exception as e:
                logging.error(f"Could not load escrow deal from {fname}: {e}")
    logging.info(f"Loaded {len(escrow_deals)} active escrow deals.")

def save_escrow_deal(deal_id):
    deal = escrow_deals.get(deal_id)
    if not deal:
        logging.warning(f"Attempted to save non-existent escrow deal: {deal_id}")
        return
    try:
        with open(os.path.join(ESCROW_DIR, f"{deal_id}.json"), "w") as f:
            json.dump(deal, f, default=str, indent=2)
    except Exception as e:
        logging.error(f"Failed to save escrow deal {deal_id}: {e}")

def save_all_escrow_deals():
    logging.info("Saving all escrow deals...")
    for deal_id in escrow_deals.keys():
        save_escrow_deal(deal_id)
    logging.info("All escrow deals saved.")

def save_group_settings(chat_id):
    settings = group_settings.get(chat_id)
    if not settings:
        return
    try:
        with open(os.path.join(GROUPS_DIR, f"{chat_id}.json"), "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save group settings for {chat_id}: {e}")

def load_all_group_settings():
    global group_settings
    logging.info("Loading all group settings...")
    for fname in os.listdir(GROUPS_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(GROUPS_DIR, fname), "r") as f:
                    settings = json.load(f)
                    chat_id = int(fname.split(".")[0])
                    group_settings[chat_id] = settings
            except Exception as e:
                logging.error(f"Could not load group settings from {fname}: {e}")
    logging.info(f"Loaded settings for {len(group_settings)} groups.")

def save_all_group_settings():
    logging.info("Saving all group settings...")
    for chat_id in group_settings.keys():
        save_group_settings(chat_id)
    logging.info("All group settings saved.")

def save_recovery_data(token_hash):
    data = recovery_data.get(token_hash)
    if not data:
        return
    try:
        with open(os.path.join(RECOVERY_DIR, f"{token_hash}.json"), "w") as f:
            json.dump(data, f, default=str, indent=2)
    except Exception as e:
        logging.error(f"Failed to save recovery data for token hash {token_hash}: {e}")

def load_all_recovery_data():
    global recovery_data
    logging.info("Loading all recovery data...")
    for fname in os.listdir(RECOVERY_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(RECOVERY_DIR, fname), "r") as f:
                    data = json.load(f)
                    token_hash = fname.split(".")[0]
                    # Convert expiry time back to datetime object
                    if 'lock_expiry' in data and data['lock_expiry']:
                        data['lock_expiry'] = datetime.fromisoformat(data['lock_expiry'])
                    recovery_data[token_hash] = data
            except Exception as e:
                logging.error(f"Could not load recovery data from {fname}: {e}")
    logging.info(f"Loaded {len(recovery_data)} recovery tokens.")

def save_all_recovery_data():
    logging.info("Saving all recovery data...")
    for token_hash in recovery_data.keys():
        save_recovery_data(token_hash)
    logging.info("All recovery data saved.")

def save_gift_code(code):
    data = gift_codes.get(code)
    if not data:
        return
    try:
        with open(os.path.join(GIFT_CODE_DIR, f"{code}.json"), "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save gift code {code}: {e}")

def load_all_gift_codes():
    global gift_codes
    logging.info("Loading all gift codes...")
    for fname in os.listdir(GIFT_CODE_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(GIFT_CODE_DIR, fname), "r") as f:
                    data = json.load(f)
                    code = fname.split(".")[0]
                    gift_codes[code] = data
            except Exception as e:
                logging.error(f"Could not load gift code from {fname}: {e}")
    logging.info(f"Loaded {len(gift_codes)} gift codes.")

def save_all_gift_codes():
    logging.info("Saving all gift codes...")
    for code in gift_codes.keys():
        save_gift_code(code)
    logging.info("All gift codes saved.")

atexit.register(save_bot_state_full)

import signal

_signal_received = False

def _signal_handler(signum, frame):
    """Best-effort sync signal handler for environments where asyncio's
    ``add_signal_handler`` isn't installed yet (e.g. before PTB / run_bots
    takes over).

    Critically, after saving we re-raise a ``KeyboardInterrupt`` so the
    Python interpreter actually unwinds the stack. The previous version
    just set ``bot_stopped = True`` and returned, which is why ``Ctrl+C``
    only printed "saving data" and the polling loop kept running until the
    user closed their terminal. ``KeyboardInterrupt`` propagates cleanly
    through ``asyncio.run`` and ``app.run_polling``, both of which handle
    it as graceful shutdown.

    A second ``Ctrl+C`` always force-exits.
    """
    global _signal_received, bot_stopped
    if _signal_received:
        # Second signal — operator wants out NOW. Skip the slow save, just
        # let Python exit. atexit will still try to flush.
        logging.warning(
            f"Received signal {signum} again — forcing immediate exit."
        )
        os._exit(130 if signum == signal.SIGINT else 143)
    _signal_received = True
    logging.info(f"Received signal {signum}, saving data before exit...")
    bot_stopped = True
    try:
        save_bot_state_full()
    except Exception:
        pass
    # Propagate as KeyboardInterrupt so the running event loop / polling
    # loop unwinds. SIGTERM also gets KeyboardInterrupt (rather than
    # SystemExit) because PTB's run_polling and our run_bots both treat
    # KeyboardInterrupt as the canonical "stop now" signal.
    raise KeyboardInterrupt()

signal.signal(signal.SIGTERM, _signal_handler)

signal.signal(signal.SIGINT, _signal_handler)

load_bot_state()

async def check_bet_limits(update: Update, bet_amount: float, game_name: str, user_id: int = None) -> bool:
    import math as _math_cbl
    if user_id is None and update.effective_user:
        user_id = update.effective_user.id
    user_lang = get_user_lang(user_id) if user_id else DEFAULT_LANG
    user_currency = get_user_currency(user_id) if user_id else "USD"

    # SECURITY: Reject NaN, Inf, negative, and zero bet amounts
    if _math_cbl.isnan(bet_amount) or _math_cbl.isinf(bet_amount) or bet_amount <= 0:
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount.")
        return False

    limits = bot_settings.get('game_limits', {}).get(game_name, {})
    min_bet = limits.get('min', MIN_BALANCE)

    # Use dynamic max bet based on house balance (overrides static limits)
    dynamic_max = get_dynamic_max_bet(game_category=None, game_type=game_name)
    static_max = limits.get('max')
    # Use the lower of static and dynamic limits (or just dynamic if no static)
    max_bet = min(dynamic_max, static_max) if static_max is not None else dynamic_max

    if bet_amount < min_bet:
        min_formatted = format_currency(min_bet, user_currency)
        await update.message.reply_text(get_text("min_bet", user_lang, amount=min_formatted))
        return False
    if max_bet is not None and bet_amount > max_bet:
        await update.message.reply_text(
            f"{pe('cross')} Maximum bet for this game is ${max_bet:,.2f}\n"
            f"Use /maxbet to see current limits.",
            parse_mode=ParseMode.HTML
        )
        return False
    return True

DYNAMIC_BET_CATEGORY_RATE = {
    "standard": 0.006,    # 0.6% of house balance
    "special": 0.003,     # 0.3% of house balance
    "pvp": None,          # No limit for PvP (player funds, not house risk)
}

GAME_TO_DYNAMIC_CATEGORY = {
    # Standard games (0.6%)
    "originals": "standard",
    "slots": "standard",
    "7up": "standard",
    "sidebets": "standard",
    # Special games (0.3%)
    "special": "special",
    # PvP (no limit)
    "pvp": "pvp",
}

GAME_TYPE_TO_DYNAMIC_CATEGORY = {
    # Standard games
    "roulette": "standard", "blackjack": "standard", "crash": "standard",
    "dice_roll": "standard", "plinko": "standard", "limbo": "standard",
    "7up7down": "standard", "7up7down_2dice": "standard", "7up7down_3dice": "standard",
    "chicken_road": "standard", "coinchain": "standard", "coin_chain": "standard",
    "coin_flip": "standard", "wheel": "standard", "scratch": "standard",
    "slots": "standard", "predict": "standard",
    "classic_rush": "standard", "odd_even_rush": "standard",
    "high_low_rush": "standard", "rainbow_rush": "standard", "blaze_rush": "standard",
    # Special games (0.3%)
    "mines": "special", "tower": "special", "keno": "special", "highlow": "special",
    # PvP games (no limit)
    "pvp_dice": "pvp", "pvp_darts": "pvp", "pvp_goal": "pvp", "pvp_bowl": "pvp",
    "xdxw_dice": "pvp", "xdxw_darts": "pvp", "xdxw_goal": "pvp", "xdxw_bowl": "pvp",
    "group_challenge_dice": "pvp", "group_challenge_darts": "pvp",
    "group_challenge_goal": "pvp", "group_challenge_bowl": "pvp",
    # PvB games use standard limits (house is at risk)
    "pvb_dice": "standard", "pvb_darts": "standard",
    "pvb_goal": "standard", "pvb_bowl": "standard",
    # Side bets
    "sidebet_win": "standard", "sidebet_lose": "standard",
}

def get_dynamic_max_bet(game_category: str = "originals", game_type: str = None) -> float:
    """Calculate max bet dynamically based on house balance.
    Returns the max bet in USD. PvP games return a very high limit (effectively unlimited)."""
    house_bal = bot_settings.get("house_balance", 100_000_000_000_000.0)

    # Determine the dynamic category
    if game_type:
        dyn_cat = GAME_TYPE_TO_DYNAMIC_CATEGORY.get(game_type, "standard")
    else:
        dyn_cat = GAME_TO_DYNAMIC_CATEGORY.get(game_category, "standard")

    rate = DYNAMIC_BET_CATEGORY_RATE.get(dyn_cat)

    if rate is None:
        # PvP: no house risk, return effectively unlimited
        return 999_999_999.0

    max_bet = house_bal * rate
    # Floor to 2 decimal places, minimum $0.10
    return max(0.10, round(max_bet, 2))

async def get_user_profile_picture(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """
    Retrieve user's Telegram profile picture and return as PIL Image.
    Returns None if no profile picture is available.
    """
    try:
        # Get user profile photos
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)

        if photos.total_count > 0:
            # Get the first (most recent) photo
            photo = photos.photos[0][-1]  # Get largest size

            # Download the photo
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = await photo_file.download_as_bytearray()

            # Convert to PIL Image
            image = Image.open(BytesIO(photo_bytes))
            return image

        return None
    except Exception as e:
        logging.error(f"Error fetching profile picture for user {user_id}: {e}")
        return None

GAME_DISPLAY_NAMES = {
    "dice": "Dice", "darts": "Darts", "goal": "Goal", "bowl": "Bowling",
    "blackjack": "Blackjack", "coinflip": "Coinflip", "roulette": "Roulette",
    "slots": "Slots", "keno": "Keno", "tower": "Tower", "highlow": "HighLow",
    "limbo": "Limbo", "predict": "Predict", "crash": "Crash", "plinko": "Plinko",
    "wheel": "Wheel", "scratch": "Scratch", "coinchain": "Coinchain", "mines": "Mines",
    "7up7down": "7Up7Down", "7up7down_original": "7Up7Down",
    "dicerush": "Dicerush", "dicerush_original": "Dicerush",
    "rush_rainbow": "Rush_Rainbow", "rush_rainbow_original": "Rush_Rainbow",
    "hi_lo": "HiLo", "aviator": "Aviator", "jetx": "JetX",
    "poker": "Poker", "baccarat": "Baccarat", "teenpatti": "Teen Patti",
    "andarbahar": "Andar Bahar", "dragon_tiger": "Dragon Tiger",
    "chicken_road": "Chicken Road",
}

_profile_pic_inflight: dict = {}  # user_id -> asyncio.Future

async def _get_cached_profile_picture(context, user_id: int):
    """Return cached profile picture or fetch a fresh one.

    PERFORMANCE: coalesces concurrent misses for the same user into a
    single ``get_user_profile_picture`` call so we never hit the
    Telegram API N times for the same avatar within a single render
    burst.
    """
    now = datetime.now().timestamp()
    cached = _profile_pic_cache.get(user_id)
    if cached:
        img, ts = cached
        if now - ts < _PROFILE_PIC_CACHE_TTL:
            return img

    inflight = _profile_pic_inflight.get(user_id)
    if inflight is not None and not inflight.done():
        try:
            return await inflight
        except Exception:
            return None

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _profile_pic_inflight[user_id] = fut
    try:
        img = await get_user_profile_picture(context, user_id)
        _profile_pic_cache[user_id] = (img, now)
        if not fut.done():
            fut.set_result(img)
        return img
    except Exception as e:
        if not fut.done():
            fut.set_exception(e)
        raise
    finally:
        _profile_pic_inflight.pop(user_id, None)

async def ensure_user_in_wallets(user_id: int, username: str = None, referrer_id: int = None, context: ContextTypes.DEFAULT_TYPE = None, first_name: str = None):
    """OPTIMIZED: Fast path for existing users, deferred API call for new users."""
    # FAST PATH: User already registered (99%+ of cases)
    # PERFORMANCE: Only save if data actually changed (avoids unnecessary dirty-marking)
    if user_id in user_stats:
        userinfo = user_stats[user_id].get('userinfo', {})
        changed = False
        # Update first_name and username only if they actually changed
        if first_name and userinfo.get('first_name') != first_name:
            userinfo['first_name'] = first_name
            changed = True
        if username and userinfo.get('username') != username:
            userinfo['username'] = username
            changed = True
        if changed:
            user_stats[user_id]['userinfo'] = userinfo
            save_user_data(user_id)
        return

    # SLOW PATH: New user registration
    # For existing users coming from update, use provided data instead of API call
    # Only fetch from API if both username and first_name are missing AND we have context
    if (not username or not first_name) and context:
        try:
            # OPTIMIZED: Use non-blocking API call with timeout
            chat_member = await context.bot.get_chat(user_id)
            if not username:
                username = chat_member.username
            if not first_name:
                first_name = chat_member.first_name
        except (BadRequest, Forbidden):
            logging.warning(f"Could not fetch user info for new user {user_id}")
        except Exception as e:
            logging.error(f"Error fetching user info for {user_id}: {e}")

    user_wallets[user_id] = {"USDT": 0.0}
    user_stats[user_id] = {
        "userinfo": {
            "user_id": user_id,
            "username": username or "",
            "first_name": first_name or "User",
            "join_date": str(datetime.now(timezone.utc)),
            "language": DEFAULT_LANG,
            "currency": "USD"
        },
        "active_currency": "USDT",
        "deposits": [], # Changed to list of dicts
        "withdrawals": [], # Changed to list of dicts
        "tips_received": {"count": 0, "amount": 0.0},
        "tips_sent": {"count": 0, "amount": 0.0},
        "bets": {"count": 0, "amount": 0.0, "wins": 0, "losses": 0, "pvp_wins": 0, "history": []},
        "rain_received": {"count": 0, "amount": 0.0},
        "wallet": 0.0,
        "pnl": 0.0,
        "last_update": str(datetime.now(timezone.utc)),
        "game_sessions": [],
        "escrow_deals": [],
        "last_win": 0.0,  # NEW: Track last win amount
        "referral": {
            "referrer_id": referrer_id,
            "referred_users": [],
            "commission_earned": 0.0,
            "code": generate_unique_referral_code(),  # NEW: User's unique referral code
            "commissions": {}  # NEW: Per-currency commission tracking
        },
        "achievements": [], # NEW
        "last_daily_claim": None, # NEW
        "recovery_token_hash": None, # NEW
        "last_weekly_claim": None, # NEW
        "last_monthly_claim": None, # NEW
        "last_rakeback_claim_wager": 0.0, # NEW
        "rakeback_balance": 0.0, # NEW: Accumulated rakeback from house edge
        "weekly_stats": {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": None}, # NEW
        "monthly_stats": {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": None}, # NEW
        "claimed_gift_codes": [], # NEW
        "claimed_level_rewards": [], # NEW: For level system
        "unwagered_deposit": 0.0, # NEW: Deposits that need 2x wagering
        "unwagered_tips": 0.0, # NEW: Tips that need 1x wagering
        "provably_fair": {  # NEW: Provably fair system
            "server_seed": generate_server_seed(),
            "server_seed_hash": None,  # Will be set when seed is revealed
            "client_seed": generate_client_seed(),
            "nonce": 0,
            "next_server_seed": generate_server_seed(),  # For rotation
        }
    }
    if username:
        username_to_userid[normalize_username(username)] = user_id

    # NEW: Register the user's referral code in the global mapping
    ref_code = user_stats[user_id]["referral"]["code"]
    referral_codes[ref_code] = user_id

    # AUTO-GENERATE RECOVERY TOKEN FOR NEW USER
    token = secrets.token_hex(20)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    recovery_data[token_hash] = {
        "user_id": user_id,
        "username": username or "",
        "created_at": str(datetime.now(timezone.utc)),
        "failed_attempts": 0,
        "lock_expiry": None
    }
    user_stats[user_id]["recovery_token_hash"] = token_hash

    save_recovery_data(token_hash)

    # Send recovery token to user
    if context:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🔐 <b>Account Recovery Token</b>\n\n"
                    "Your account recovery token has been generated. Please save this token in a secure place. "
                    "It is the ONLY way to recover your account if you lose access to your Telegram account.\n\n"
                    "<b>⚠️ IMPORTANT:</b>\n"
                    "• Do NOT share this token with anyone\n"
                    "• Save it in a safe place offline\n"
                    "• You will need this token to use /recover command\n\n"
                    "<b>Your Recovery Token:</b>\n"
                    f"<code>{token}</code>\n\n"
                    "This message will only be sent once. Make sure to save it now!"
                ),
                parse_mode=ParseMode.HTML
            )
        except (BadRequest, Forbidden):
            logging.warning(f"Could not send recovery token to user {user_id}")

        if referrer_id:
            await ensure_user_in_wallets(referrer_id, context=context) # Pass context
            if 'referral' not in user_stats[referrer_id]:
                 user_stats[referrer_id]['referral'] = {"referrer_id": None, "referred_users": [], "commission_earned": 0.0, "code": generate_unique_referral_code(), "commissions": {}}
                 # Register the code
                 ref_code = user_stats[referrer_id]['referral']['code']
                 referral_codes[ref_code] = referrer_id
            # Ensure commissions dict exists for existing users
            if 'commissions' not in user_stats[referrer_id]['referral']:
                user_stats[referrer_id]['referral']['commissions'] = {}
            user_stats[referrer_id]['referral']['referred_users'].append(user_id)
            save_user_data(referrer_id)
            await check_and_award_achievements(referrer_id, None) # Check for referral achievements
        save_user_data(user_id)
        logging.info(f"New user registered: {username} ({user_id})")

    # Update username and first_name if they have changed
    current_username = user_stats[user_id]["userinfo"].get("username")
    if username and current_username != username:
        # Remove old username mapping if it exists
        if current_username and normalize_username(current_username) in username_to_userid:
            del username_to_userid[normalize_username(current_username)]
        user_stats[user_id]["userinfo"]["username"] = username
        username_to_userid[normalize_username(username)] = user_id
        save_user_data(user_id)

    # Update first_name if provided and different
    if first_name:
        current_first_name = user_stats[user_id]["userinfo"].get("first_name")
        if current_first_name != first_name:
            user_stats[user_id]["userinfo"]["first_name"] = first_name
            save_user_data(user_id)

    # Initialize last_win if it doesn't exist (for existing users)
    if "last_win" not in user_stats[user_id]:
        user_stats[user_id]["last_win"] = 0.0
        save_user_data(user_id)

    # Initialize provably fair data if it doesn't exist (for existing users - migration)
    if "provably_fair" not in user_stats[user_id]:
        user_stats[user_id]["provably_fair"] = {
            "server_seed": generate_server_seed(),
            "server_seed_hash": None,
            "client_seed": generate_client_seed(),
            "nonce": 0,
            "next_server_seed": generate_server_seed(),
        }
        save_user_data(user_id)

    # Initialize unwagered fields if they don't exist (for existing users)
    if "unwagered_deposit" not in user_stats[user_id]:
        user_stats[user_id]["unwagered_deposit"] = 0.0
    if "unwagered_tips" not in user_stats[user_id]:
        user_stats[user_id]["unwagered_tips"] = 0.0
        save_user_data(user_id)

    return True

def set_menu_owner(message, user_id):
    """
    Set the owner of a menu message.
    Should be called after sending a message with inline keyboard.
    OPTIMIZED: Stores in memory with TTL expiry instead of bot_settings.
    """
    menu_key = f"{message.chat_id}_{message.message_id}"
    expiry = datetime.now().timestamp() + _MENU_OWNER_TTL
    _menu_owners[menu_key] = (user_id, expiry)

async def send_insufficient_balance_message(update: Update, message: str = None, user_lang: str = None):
    """
    Send an insufficient balance message.
    Can be used with update.message or update.callback_query.
    """
    if user_lang is None:
        user = update.effective_user
        user_lang = get_user_lang(user.id) if user else DEFAULT_LANG

    if message is None:
        message = get_text("insufficient_balance", user_lang)

    # Add currency change hint
    message += "\n(or please change the currency from settings.)"

    if update.callback_query:
        await safe_edit_message(update.callback_query, message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def check_and_award_achievements(user_id, context, multiplier=0):
    if user_id not in user_stats:
        return

    stats = user_stats[user_id]
    if "achievements" not in stats:
        stats["achievements"] = []
    user_achievements = stats["achievements"]

    total_wagered = stats["bets"]["amount"]
    total_wins = stats["bets"]["wins"]
    pvp_wins = stats["bets"].get("pvp_wins", 0)
    referrals = len(stats.get("referral", {}).get("referred_users", []))

    for achievement_id, ach_data in ACHIEVEMENTS.items():
        if achievement_id in user_achievements:
            continue # Already has it

        unlocked = False
        if ach_data["type"] == "wager" and total_wagered >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "wins" and total_wins >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "pvp_wins" and pvp_wins >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "multiplier" and multiplier >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "referrals" and referrals >= ach_data["value"]:
            unlocked = True

        if unlocked:
            stats["achievements"].append(achievement_id)
            save_user_data(user_id)
            if context:
                lang = stats.get("userinfo", {}).get("language", DEFAULT_LANG)
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=get_text("achievement_unlocked", lang, emoji=ach_data["emoji"], name=ach_data["name"], description=ach_data["description"]),
                        parse_mode=ParseMode.HTML
                    )
                except (BadRequest, Forbidden):
                    logging.warning(f"Could not send achievement notification to user {user_id}")

JACKPOT_FILE = os.path.join(DATA_DIR, "jackpot.json")

JACKPOT_DEFAULT_THRESHOLD_USD = 100.0    # 7-day wager required to be eligible

JACKPOT_DEFAULT_ACCUM_RATE = 0.002        # 0.2 % of every bet -> jackpot

JACKPOT_DRAW_HOUR_IST = 17                # 5:30 PM IST

JACKPOT_DRAW_MINUTE_IST = 30

JACKPOT_ANNOUNCE_CHAT = os.environ.get("JACKPOT_ANNOUNCE_CHAT", "@playcsino")

JACKPOT_HISTORY_LIMIT = 50

_JACKPOT_IST_OFFSET = timedelta(hours=5, minutes=30)

_jackpot_lock = asyncio.Lock()

_jackpot_dirty = False

_jackpot_state = {
    "pool": 0.0,
    "wager_threshold": JACKPOT_DEFAULT_THRESHOLD_USD,
    "accum_rate": JACKPOT_DEFAULT_ACCUM_RATE,
    "user_wagers": {},          # str(user_id) -> {"YYYY-MM-DD": float}
    "last_winner": None,        # {user_id, username, amount, draw_iso, pool}
    "history": [],              # last N draws
    "last_draw_iso": None,
}

_jackpot_loaded = False

def _jackpot_load():
    """Load jackpot state from disk. Idempotent and safe to call early."""
    global _jackpot_loaded
    if _jackpot_loaded:
        return
    _jackpot_loaded = True
    try:
        if os.path.exists(JACKPOT_FILE):
            with open(JACKPOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in ("pool", "wager_threshold", "accum_rate"):
                if k in data:
                    try:
                        _jackpot_state[k] = float(data[k])
                    except (TypeError, ValueError):
                        pass
            if isinstance(data.get("user_wagers"), dict):
                _jackpot_state["user_wagers"] = data["user_wagers"]
            if isinstance(data.get("last_winner"), dict):
                _jackpot_state["last_winner"] = data["last_winner"]
            if isinstance(data.get("history"), list):
                _jackpot_state["history"] = data["history"][-JACKPOT_HISTORY_LIMIT:]
            _jackpot_state["last_draw_iso"] = data.get("last_draw_iso")
            logging.info(
                "Jackpot loaded: pool=$%.2f threshold=$%.2f rate=%.4f users=%d",
                _jackpot_state["pool"], _jackpot_state["wager_threshold"],
                _jackpot_state["accum_rate"], len(_jackpot_state["user_wagers"]),
            )
    except Exception as e:
        logging.error(f"Failed to load jackpot state: {e}")

def _jackpot_mark_dirty():
    global _jackpot_dirty
    _jackpot_dirty = True

def _jackpot_eligible_entries():
    """Return list of (user_id_int, weight_float, username_str) for users
    whose 7-day wager >= threshold."""
    _jackpot_load()
    threshold = float(_jackpot_state.get("wager_threshold", JACKPOT_DEFAULT_THRESHOLD_USD))
    out = []
    for key, bucket in list(_jackpot_state["user_wagers"].items()):
        try:
            uid = int(key)
        except (TypeError, ValueError):
            continue
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        total = 0.0
        if isinstance(bucket, dict):
            for d, v in bucket.items():
                if d > cutoff:
                    try:
                        total += float(v)
                    except (TypeError, ValueError):
                        pass
        if total >= threshold:
            uname = ""
            try:
                uname = (user_stats.get(uid, {}).get("userinfo", {}) or {}).get("username") or ""
            except Exception:
                uname = ""
            out.append((uid, total, uname))
    return out

def _jackpot_pick_winner(entries):
    """Weighted random pick. Returns (uid, weight, username) or None."""
    if not entries:
        return None
    total_w = sum(e[1] for e in entries)
    if total_w <= 0:
        return None
    r = random.uniform(0, total_w)
    upto = 0.0
    for entry in entries:
        upto += entry[1]
        if r <= upto:
            return entry
    return entries[-1]

def _jackpot_next_draw_dt(now_utc=None):
    """Return the next 5:30 PM IST datetime (UTC) at or after ``now_utc``."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + _JACKPOT_IST_OFFSET
    target_ist = now_ist.replace(
        hour=JACKPOT_DRAW_HOUR_IST, minute=JACKPOT_DRAW_MINUTE_IST,
        second=0, microsecond=0,
    )
    if target_ist <= now_ist:
        target_ist = target_ist + timedelta(days=1)
    return target_ist - _JACKPOT_IST_OFFSET

async def _jackpot_run_draw(application):
    """Perform the daily jackpot draw. Awards the pool to the winner,
    resets the pool to zero, announces in the configured group."""
    async with _jackpot_lock:
        _jackpot_load()
        pool = float(_jackpot_state.get("pool", 0.0) or 0.0)
        threshold = float(_jackpot_state.get("wager_threshold", JACKPOT_DEFAULT_THRESHOLD_USD))
        entries = _jackpot_eligible_entries()
        now_utc = datetime.now(timezone.utc)
        draw_iso = now_utc.isoformat()

        if not entries or pool <= 0:
            logging.info(
                "Jackpot draw skipped: pool=$%.2f eligible=%d threshold=$%.2f",
                pool, len(entries), threshold,
            )
            _jackpot_state["last_draw_iso"] = draw_iso
            _jackpot_mark_dirty()
            try:
                await asyncio.get_running_loop().run_in_executor(_save_executor, _jackpot_save_now)
            except Exception:
                pass
            return None

        winner = _jackpot_pick_winner(entries)
        if winner is None:
            return None
        uid, weight, uname = winner
        amount_won = pool

        # Credit the winner.
        try:
            credit_wallet_safe(uid, amount_won)
            try:
                save_user_data(uid)
            except Exception:
                pass
        except Exception as e:
            logging.error(f"Failed to credit jackpot winner {uid}: {e}")
            return None

        # Reset the pool.
        _jackpot_state["pool"] = 0.0
        winner_record = {
            "user_id": uid,
            "username": uname,
            "amount": amount_won,
            "pool": amount_won,
            "draw_iso": draw_iso,
            "weight": weight,
        }
        _jackpot_state["last_winner"] = winner_record
        _jackpot_state["last_draw_iso"] = draw_iso
        history = _jackpot_state.setdefault("history", [])
        history.append(winner_record)
        if len(history) > JACKPOT_HISTORY_LIMIT:
            del history[: -JACKPOT_HISTORY_LIMIT]
        _jackpot_mark_dirty()
        try:
            await asyncio.get_running_loop().run_in_executor(_save_executor, _jackpot_save_now)
        except Exception:
            pass

        # Announce the winner in @PlayCasino.
        try:
            bot_uname = await get_bot_username(type("ctx", (), {"bot": application.bot})())
        except Exception:
            bot_uname = "Casino"
        try:
            winner_pic = await _get_cached_profile_picture(
                type("ctx", (), {"bot": application.bot})(), uid
            )
        except Exception:
            winner_pic = None

        try:
            loop = asyncio.get_running_loop()
            img_buf = await loop.run_in_executor(
                _image_executor,
                generate_jackpot_winner_image,
                uname or f"User-{uid}",
                amount_won,
                bot_uname,
                winner_pic,
                draw_iso,
            )
        except Exception as e:
            logging.error(f"Failed to render jackpot winner image: {e}")
            img_buf = None

        # Next-draw timestamp, shown in IST (this is the draw cadence).
        next_draw_dt = _jackpot_next_draw_dt(now_utc)
        next_draw_ist = (next_draw_dt + _JACKPOT_IST_OFFSET).strftime("%b %d, %Y \u2022 %H:%M IST")

        # Public broadcast shows the amount in USD (common denominator)
        # because the announcement chat contains users on all different
        # display currencies. Premium emojis throughout.
        mention = f"@{uname}" if uname else f"<a href=\"tg://user?id={uid}\">player</a>"
        caption = (
            f"{pe('trophy')} <b>JACKPOT WINNER!</b> {pe('fire')}\n\n"
            f"{mention} just won <b>${amount_won:,.2f}</b> from the daily jackpot! {pe('money')}\n\n"
            f"{pe('refresh')} The jackpot pool has been <b>reset to zero</b>.\n"
            f"{pe('clock')} Next draw: <b>{next_draw_ist}</b> \u2014 every bet counts!\n\n"
            f"{pe('rocket')} Play more, wager more, and you could be next."
        )

        posted_msg_id = None
        try:
            if img_buf is not None:
                sent = await application.bot.send_photo(
                    chat_id=JACKPOT_ANNOUNCE_CHAT,
                    photo=img_buf,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await application.bot.send_message(
                    chat_id=JACKPOT_ANNOUNCE_CHAT,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                )
            posted_msg_id = getattr(sent, "message_id", None)
        except Exception as e:
            logging.error(f"Failed to announce jackpot winner in {JACKPOT_ANNOUNCE_CHAT}: {e}")

        # Pin the winner announcement so it stays visible until the next draw.
        if posted_msg_id is not None:
            try:
                await application.bot.pin_chat_message(
                    chat_id=JACKPOT_ANNOUNCE_CHAT,
                    message_id=posted_msg_id,
                    disable_notification=False,
                )
            except Exception as e:
                logging.warning(
                    f"Failed to pin jackpot winner message in {JACKPOT_ANNOUNCE_CHAT}: {e}"
                )

        # Best-effort DM to the winner, in THEIR display currency.
        try:
            winner_display = format_for_user(uid, amount_won, with_usdt_estimate=True)
            await application.bot.send_message(
                chat_id=uid,
                text=(
                    f"{pe('trophy')} You just won the daily jackpot \u2014 "
                    f"<b>{winner_display}</b> has been credited to your wallet. {pe('money')}"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        logging.info(
            "Jackpot drawn: winner=%s amount=$%.2f eligible=%d",
            uname or uid, amount_won, len(entries),
        )
        return winner_record

async def _jackpot_scheduler_task(application):
    """Sleeps until the next 5:30 PM IST, runs the draw, repeats. Runs as a
    long-lived task started from ``post_init``."""
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            next_dt = _jackpot_next_draw_dt(now_utc)
            wait_s = max(1.0, (next_dt - now_utc).total_seconds())
            logging.info(
                "Jackpot scheduler: next draw at %s UTC (%.0fs)",
                next_dt.isoformat(timespec="seconds"), wait_s,
            )
            await asyncio.sleep(wait_s)
            try:
                await _jackpot_run_draw(application)
            except Exception as e:
                logging.error(f"Jackpot draw error: {e}", exc_info=True)
            # Small buffer so we don't immediately re-trigger if the draw
            # finishes within the same minute.
            await asyncio.sleep(65)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Jackpot scheduler crashed: {e}", exc_info=True)
            await asyncio.sleep(60)

def _jackpot_prune_all():
    """Drop every user-wager bucket entry older than 7 days. Keeps the
    jackpot state file from growing unbounded as inactive users
    accumulate stale day-buckets."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    user_wagers = _jackpot_state.get("user_wagers", {})
    if not isinstance(user_wagers, dict):
        return
    pruned_users = 0
    for key in list(user_wagers.keys()):
        bucket = user_wagers.get(key)
        if not isinstance(bucket, dict):
            user_wagers.pop(key, None)
            pruned_users += 1
            continue
        cleaned = {d: v for d, v in bucket.items() if d > cutoff}
        if cleaned:
            user_wagers[key] = cleaned
        else:
            user_wagers.pop(key, None)
            pruned_users += 1
    if pruned_users:
        _jackpot_mark_dirty()

async def _jackpot_save_loop():
    """Background loop that persists jackpot state when dirty (every 30s)
    and prunes stale user-wager buckets (every 5 minutes)."""
    last_prune_at = 0.0
    while True:
        try:
            await asyncio.sleep(30)
            try:
                import time as _t
                now_mono = _t.monotonic()
                if now_mono - last_prune_at > 300:
                    last_prune_at = now_mono
                    _jackpot_prune_all()
            except Exception as e:
                logging.error(f"Jackpot prune failed: {e}")
            if _jackpot_dirty:
                try:
                    await asyncio.get_running_loop().run_in_executor(_save_executor, _jackpot_save_now)
                except Exception as e:
                    logging.error(f"Jackpot background save failed: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Jackpot save loop error: {e}")

BJ_CARD_W = 78    # card width in pixels

BJ_CARD_H = 110   # card height in pixels

BJ_CARD_RADIUS = 10

BJ_TABLE_COLOR = (8, 12, 28)           # Very dark blue-black

BJ_FELT_LINE   = (20, 35, 70)          # Subtle blue grid lines

BJ_ACCENT      = (0, 180, 255)         # Neon blue accent

BJ_CARD_BG     = (255, 255, 255)     # white card face

BJ_CARD_BACK   = (20, 30, 90)        # dark navy card back

BJ_RED         = (204, 0, 0)         # red suits

BJ_BLACK_SUIT  = (15, 15, 15)        # black suits

BJ_TEXT_WHITE  = (240, 240, 255)     # Soft white

BJ_TEXT_GOLD   = (255, 215, 0)       # Gold text

BJ_TEXT_LIGHT  = (140, 160, 200)     # Dim blue-gray

BJ_TEXT_DIM    = (80, 100, 140)      # Dimmer text

BJ_WIN_COLOR   = (0, 255, 120)       # Neon green

BJ_LOSE_COLOR  = (255, 60, 60)       # Red

BJ_PUSH_COLOR  = (220, 190, 50)      # Gold/yellow

BJ_BORDER      = (30, 60, 120)       # Border blue

DR_BG_COLOR = (12, 12, 30)             # Very dark blue-black

DR_ACCENT = (0, 150, 255)              # Neon blue

DR_GOLD = (255, 215, 0)                # Gold

DR_GREEN = (0, 255, 120)               # Win green

DR_RED = (255, 60, 60)                 # Loss red

DR_TEXT_WHITE = (240, 240, 255)        # Soft white

DR_TEXT_DIM = (140, 160, 200)          # Dim blue-gray

DR_TEXT_GOLD = (255, 215, 0)           # Gold text

DR_BORDER = (30, 60, 120)              # Border blue

DR_ORANGE = (255, 165, 0)              # Orange for highlights

DR_PURPLE = (138, 43, 226)             # Purple for rainbow

LIMBO_BG_COLOR = (8, 12, 28)           # Very dark blue-black

LIMBO_ACCENT = (0, 180, 255)            # Neon blue

LIMBO_GREEN = (0, 255, 120)             # Neon green (multiplier)

LIMBO_GOLD = (255, 215, 0)              # Gold text

LIMBO_WIN = (0, 255, 120)               # Win green

LIMBO_LOSE = (255, 60, 60)              # Loss red

LIMBO_TEXT_WHITE = (240, 240, 255)      # Soft white

LIMBO_TEXT_DIM = (140, 160, 200)        # Dim blue-gray

LIMBO_CARD_BG = (15, 25, 50)            # Card background

LIMBO_BORDER = (30, 60, 120)            # Border blue

_limbo_font_cache = {}

CARD_EMOJIS = {
    1: "🂡",   # Ace of Spades
    2: "🂢",   # 2 of Spades
    3: "🂣",   # 3 of Spades
    4: "🂤",   # 4 of Spades
    5: "🂥",   # 5 of Spades
    6: "🂦",   # 6 of Spades
    7: "🂧",   # 7 of Spades
    8: "🂨",   # 8 of Spades
    9: "🂩",   # 9 of Spades
    10: "🂪",  # 10 of Spades
    11: "🂫",  # Jack of Spades
    12: "🂭",  # Queen of Spades
    13: "🂮",  # King of Spades
}

ROULETTE_RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]

ROULETTE_BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

DICE_RUSH_EMOJI = "🎲"

MULTI_ROLL_EMOJI = "🎲"

ZWNBSP = "\u2060"  # Zero-width space to make empty buttons work

TILE = {
    "blank": ZWNBSP,
    "play": "🟩",      # Clickable tile for the current level
    "safe": "🌴",      # Successfully stepped tile
    "snake": "🐍",     # Game Over snake
    "lock": "☁️",      # Unreached levels
}

def extract_game_name(game_type: str) -> str:
    """Extract readable game name from game_type string.

    Args:
        game_type: The internal game type identifier (e.g., 'pvp_dice', 'pvb_bowl', 'group_challenge_darts')

    Returns:
        The human-readable game name in uppercase (e.g., 'DICE', 'BOWL', 'DARTS')
    """
    return game_type.replace('pvp_', '').replace('pvb_', '').replace('group_challenge_', '').replace('xdxw_', '').upper()

def get_user_active_emoji_game(user_id: int):
    """Check if a user has any ongoing PvP or PvB emoji game.
    PERFORMANCE: Uses _user_active_games_index for O(1) lookup instead of scanning all sessions.

    Args:
        user_id: The Telegram user ID to check

    Returns:
        A tuple of (game_id: str, game_type: str) if an active game exists, otherwise (None, None)
    """
    # Fast path: check PvB games first (O(1))
    if user_id in active_pvb_games:
        game_id = active_pvb_games[user_id]
        if game_id in game_sessions and game_sessions[game_id].get('status') == 'active':
            game_type = game_sessions[game_id].get('game_type', '')
            return (game_id, game_type)

    # Fast path: check indexed active games (O(k) where k = user's active games, typically 0-1)
    indexed_games = _get_user_active_game_ids(user_id)
    if indexed_games:
        for game_id in indexed_games:
            game_data = game_sessions.get(game_id)
            if not game_data or game_data.get('status') != 'active':
                continue
            game_type = game_data.get('game_type', '')
            if any(x in game_type for x in ['pvp_dice', 'pvp_darts', 'pvp_goal', 'pvp_bowl',
                                             'pvb_dice', 'pvb_darts', 'pvb_goal', 'pvb_bowl',
                                             'group_challenge_', 'xdxw_']):
                return (game_id, game_type)

    # Fallback: full scan for backward compatibility (handles games indexed before this change)
    for game_id, game_data in game_sessions.items():
        if game_data.get('status') == 'active':
            game_type = game_data.get('game_type', '')
            if any(x in game_type for x in ['pvp_dice', 'pvp_darts', 'pvp_goal', 'pvp_bowl',
                                             'pvb_dice', 'pvb_darts', 'pvb_goal', 'pvb_bowl',
                                             'group_challenge_', 'xdxw_']):
                if 'players' in game_data and user_id in game_data['players']:
                    # Backfill the index
                    _index_user_game(user_id, game_id)
                    return (game_id, game_type)
                elif 'user_id' in game_data and game_data['user_id'] == user_id:
                    _index_user_game(user_id, game_id)
                    return (game_id, game_type)

    return (None, None)

async def create_reply_pvp_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    """Create a PvP challenge by replying to another player's message.

    Shows styled buttons:
    - Green 'Confirm' button (only challenged player can tap)
    - Blue 'Play with Bot' button with premium bot emoji (only challenger can tap)
    - Red 'Cancel' button with premium X emoji (only challenger can tap)
    """
    user = update.effective_user
    replied_msg = update.message.reply_to_message
    target_user = replied_msg.from_user

    # Cannot challenge yourself
    if target_user.id == user.id:
        await update.message.reply_text(
            f"{pe('cross')} You cannot challenge yourself!",
            parse_mode=ParseMode.HTML
        )
        return

    # Cannot challenge bots
    if target_user.is_bot:
        await update.message.reply_text(
            f"{pe('cross')} You cannot challenge a bot user. Use 'Play with Bot' instead!",
            parse_mode=ParseMode.HTML
        )
        return

    message_text = update.message.text.strip().split()
    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(message_text[1], user.id)
    except (ValueError, IndexError):
        await update.message.reply_text(
            f"{pe('cross')} Invalid bet amount.\n"
            f"Usage: Reply to a player's message with <code>/{game_type} amount</code>",
            parse_mode=ParseMode.HTML
        )
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    if not await check_bet_limits(update, bet_amount_usd, f'pvp_{game_type}'):
        return

    await ensure_user_in_wallets(target_user.id, target_user.username, context=context)

    # Check if target has enough balance
    if get_active_balance_usd(target_user.id) < bet_amount_usd:
        await update.message.reply_text(
            f"{pe('cross')} {target_user.mention_html()} does not have enough balance for this challenge.",
            parse_mode=ParseMode.HTML
        )
        return

    # Check if target has ongoing game
    ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(target_user.id)
    if ongoing_game_id:
        game_name = extract_game_name(ongoing_game_type)
        await update.message.reply_text(
            f"{pe('warning')} {target_user.mention_html()} already has an ongoing <b>{game_name}</b> match.\n"
            f"They need to complete it first!",
            parse_mode=ParseMode.HTML
        )
        return

    # Create the match
    match_id = generate_unique_id("RPV")  # RPV = Reply PvP
    emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
    emoji = emoji_map.get(game_type, "\U0001f3b2")
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    game_sessions[match_id] = {
        "id": match_id,
        "game_type": f"pvp_{game_type}",
        "chat_id": update.effective_chat.id,
        "host_id": user.id,
        "host_username": normalize_username(user.username) or f"User_{user.id}",
        "opponent_id": target_user.id,
        "opponent_username": normalize_username(target_user.username) or f"User_{target_user.id}",
        "bet_amount_usd": bet_amount_usd,
        "bet_amount": bet_amount_usd,
        "bet_amount_currency": bet_amount_currency,
        "currency": currency,
        "mode": None,  # Will be set during mode selection
        "game_rolls": 1,  # Default, will be set during setup
        "target_score": 1,  # Default, will be set during setup
        "status": "pending_reply_challenge",
        "timestamp": str(datetime.now(timezone.utc)),
        "round_timeout": default_round_timeout,
        "command_message_id": update.message.message_id,
        "players": [user.id, target_user.id],
        "usernames": {
            user.id: normalize_username(user.username) or f"ID{user.id}",
            target_user.id: normalize_username(target_user.username) or f"ID{target_user.id}"
        },
    }

    # PERFORMANCE: Proactively index both players so message_listener's
    # per-user games lookup is O(1) from the first roll onward.
    _index_user_game(user.id, match_id)
    _index_user_game(target_user.id, match_id)

    # Store in user's game sessions
    if 'game_sessions' not in user_stats.get(user.id, {}):
        user_stats.setdefault(user.id, {})['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(match_id)
    save_user_data(user.id)

    # Build styled buttons
    # Green Confirm button - only challenged player can tap
    confirm_btn = apply_button_style(
        InlineKeyboardButton(f"Confirm", callback_data=f"rpvp_confirm_{match_id}"),
        'success', peb('confirm')
    )
    # Red Cancel button - only challenger can tap
    cancel_btn = apply_button_style(
        InlineKeyboardButton(f"Cancel", callback_data=f"rpvp_cancel_{match_id}"),
        'danger', peb('cross')
    )

    keyboard = create_styled_keyboard([
        [confirm_btn],
        [cancel_btn]
    ])

    sent_message = await update.message.reply_text(
        f"{pe(game_type)} <b>{game_type.upper()} PVP CHALLENGE!</b> {pe(game_type)}\n\n"
        f"{pe('lightning')} <b>Challenger:</b> {user.mention_html()}\n"
        f"{pe('target')} <b>Challenged:</b> {target_user.mention_html()}\n"
        f"{pe('money')} <b>Bet:</b> {currency_symbol}{bet_amount_currency:.2f}\n"
        f"\U0001f194 Match ID: <code>{match_id}</code>\n\n"
        f"{target_user.mention_html()}, tap {pe('confirm')} <b>Confirm</b> to accept this challenge!\n"
        f"Or {user.mention_html()} can {pe('cross')} <b>Cancel</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def create_reply_pvp_challenge_xdxw(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    """Create a PvP challenge by replying to another player's message with XdX'w format.
    Rolls and target are pre-set from the format; host picks mode after opponent confirms."""
    user = update.effective_user
    replied_msg = update.message.reply_to_message
    target_user = replied_msg.from_user

    if target_user.id == user.id:
        await update.message.reply_text(f"{pe('cross')} You cannot challenge yourself!", parse_mode=ParseMode.HTML)
        return
    if target_user.is_bot:
        await update.message.reply_text(f"{pe('cross')} You cannot challenge a bot user.", parse_mode=ParseMode.HTML)
        return

    parsed = parse_xdxw_format(update.message.text)
    if not parsed:
        await update.message.reply_text(f"{pe('cross')} Invalid XdX'w format.", parse_mode=ParseMode.HTML)
        return

    bet_str, rolls, target = parsed
    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(bet_str, user.id)
    except (ValueError, IndexError):
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount.", parse_mode=ParseMode.HTML)
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return
    if not await check_bet_limits(update, bet_amount_usd, f'pvp_{game_type}'):
        return

    await ensure_user_in_wallets(target_user.id, target_user.username, context=context)
    if get_active_balance_usd(target_user.id) < bet_amount_usd:
        await update.message.reply_text(
            f"{pe('cross')} {target_user.mention_html()} does not have enough balance for this challenge.",
            parse_mode=ParseMode.HTML)
        return

    ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(target_user.id)
    if ongoing_game_id:
        game_name = extract_game_name(ongoing_game_type)
        await update.message.reply_text(
            f"{pe('warning')} {target_user.mention_html()} already has an ongoing <b>{game_name}</b> match.\n"
            f"They need to complete it first!", parse_mode=ParseMode.HTML)
        return

    match_id = generate_unique_id("RPV")
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    game_sessions[match_id] = {
        "id": match_id,
        "game_type": f"pvp_{game_type}",
        "chat_id": update.effective_chat.id,
        "host_id": user.id,
        "host_username": normalize_username(user.username) or f"User_{user.id}",
        "opponent_id": target_user.id,
        "opponent_username": normalize_username(target_user.username) or f"User_{target_user.id}",
        "bet_amount_usd": bet_amount_usd,
        "bet_amount": bet_amount_usd,
        "bet_amount_currency": bet_amount_currency,
        "currency": currency,
        "mode": None,
        "game_rolls": rolls,
        "target_score": target,
        "status": "pending_reply_challenge",
        "timestamp": str(datetime.now(timezone.utc)),
        "round_timeout": default_round_timeout,
        "command_message_id": update.message.message_id,
        "players": [user.id, target_user.id],
        "usernames": {
            user.id: normalize_username(user.username) or f"ID{user.id}",
            target_user.id: normalize_username(target_user.username) or f"ID{target_user.id}"
        },
        "xdxw_preset": True,
    }

    _index_user_game(user.id, match_id)
    _index_user_game(target_user.id, match_id)

    if 'game_sessions' not in user_stats.get(user.id, {}):
        user_stats.setdefault(user.id, {})['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(match_id)
    save_user_data(user.id)

    confirm_btn = apply_button_style(
        InlineKeyboardButton(f"Confirm", callback_data=f"rpvp_confirm_{match_id}"),
        'success', peb('confirm')
    )
    cancel_btn = apply_button_style(
        InlineKeyboardButton(f"Cancel", callback_data=f"rpvp_cancel_{match_id}"),
        'danger', peb('cross')
    )
    keyboard = create_styled_keyboard([[confirm_btn], [cancel_btn]])

    sent_message = await update.message.reply_text(
        f"{pe(game_type)} <b>{game_type.upper()} PVP CHALLENGE!</b> {pe(game_type)}\n\n"
        f"{pe('lightning')} <b>Challenger:</b> {user.mention_html()}\n"
        f"{pe('target')} <b>Challenged:</b> {target_user.mention_html()}\n"
        f"{pe('money')} <b>Bet:</b> {currency_symbol}{bet_amount_currency:.2f}\n"
        f"{pe('rolls')} <b>Rolls:</b> {rolls} per round\n"
        f"{pe('trophy')} <b>First to:</b> {target}\n"
        f"\U0001f194 Match ID: <code>{match_id}</code>\n\n"
        f"{target_user.mention_html()}, tap {pe('confirm')} <b>Confirm</b> to accept this challenge!\n"
        f"Or {user.mention_html()} can {pe('cross')} <b>Cancel</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def darts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    message_text = update.message.text.strip().split()

    # Check for ongoing game before starting a new one
    if len(message_text) > 1:
        ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
        if ongoing_game_id:
            game_name = extract_game_name(ongoing_game_type)
            await update.message.reply_text(
                f"{pe('warning')} You already have an ongoing <b>{game_name}</b> match (ID: <code>{ongoing_game_id}</code>).\n\n"
                f"Please complete it first before starting a new game!",
                parse_mode=ParseMode.HTML
            )
            return

    # NEW: Reply-to-message PvP challenge (also supports XdX'w format when replying)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        if len(message_text) == 2:
            await create_reply_pvp_challenge(update, context, "darts")
            return
        if len(message_text) == 3 and parse_xdxw_format(update.message.text):
            await create_reply_pvp_challenge_xdxw(update, context, "darts")
            return

    # Check for XdX'w format: /darts amount XdX'w
    if len(message_text) == 3:
        await create_xdxw_challenge(update, context, "darts")
        return

    # `/dice <amount>` (and the other emoji-game equivalents) used to
    # require a group/supergroup chat. In DMs it fell through to the
    # PvP usage handler and just printed help text, which surprised
    # users. Now we route the same single-amount form through the
    # group_challenge flow in private chats too — the resulting
    # mode/rolls/target setup ends with the same Play-with-Bot button
    # the user already knows from groups.
    if len(message_text) == 2:
        await create_group_challenge(update, context, "darts")
        return

    # Check if arguments are provided (PvP format)
    if len(message_text) > 1:
        await generic_emoji_game_command(update, context, "darts")
        return

    # No arguments — show help menu
    await update.message.reply_text(
        "🎯 <b>DARTS GAME</b>\n\n"
        "Throw darts against other players and win real money!\n\n"
        "<b>How to play:</b>\n"
        "• <code>/darts amount XdX'w</code> — Challenge with dice format\n"
        "  Example: <code>/darts 10 2d3w</code> (bet $10, 2 rolls, first to 3 wins)\n\n"
        "• <code>/darts @username amount MX ftY</code> — Challenge a specific player\n"
        "  Example: <code>/darts @player 10 MX ft5</code>\n\n"
        "• In groups: <code>/darts amount</code> — Open challenge for anyone to join\n\n"
        "<b>Rules:</b>\n"
        "• XdX'w format: X = number of rolls (1-3), X' = wins needed (1-10)\n"
        "• MX = Max rounds, ftY = First to Y score\n"
        "• Winner takes the pot (minus house fee)\n\n"
        "💡 Use these commands to start a game. No inline setup needed!",
        parse_mode=ParseMode.HTML
    )

def parse_xdxw_format(command_text: str):
    """
    Parse XdX'w format from command like: /dice 10 2d3w
    Returns: (bet_amount_str, rolls, target) or None if invalid
    """
    parts = command_text.strip().split()
    if len(parts) != 3:
        return None

    # parts[0] = command, parts[1] = bet amount, parts[2] = XdX'w format
    bet_str = parts[1]
    format_str = parts[2].lower()

    # Parse XdX'w format (e.g., "2d3w" = 2 rolls, first to 3)
    if 'd' not in format_str or 'w' not in format_str:
        return None

    try:
        rolls_str, target_str = format_str.split('d')
        target_str = target_str.replace('w', '')

        rolls = int(rolls_str)
        target = int(target_str)

        # Validate ranges
        if rolls < 1 or rolls > 3:
            return None
        if target < 1 or target > 10:
            return None

        return (bet_str, rolls, target)
    except (ValueError, IndexError):
        return None

async def create_xdxw_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    """Create a challenge with XdX'w format: /dice 10 2d3w"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    parsed = parse_xdxw_format(update.message.text)
    if not parsed:
        await update.message.reply_text(
            f"{pe('cross')} Invalid format!\n\n"
            f"Usage: /{game_type} <amount> XdX'w\n"
            f"Example: /{game_type} 10 2d3w\n\n"
            f"Where:\n"
            f"• X = number of rolls (1-3)\n"
            f"• X' = first to win (1-10)\n\n"
            f"Examples:\n"
            f"• /{game_type} 5 1d1w - 1 roll, first to 1 wins\n"
            f"• /{game_type} 10 2d3w - 2 rolls, first to 3 wins\n"
            f"• /{game_type} all 3d5w - 3 rolls, first to 5 wins"
        )
        return

    bet_str, rolls, target = parsed

    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(bet_str, user.id)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount. Please enter a number or 'all'.")
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    # Store challenge data in context for mode selection
    context.user_data['xdxw_challenge'] = {
        'game_type': game_type,
        'bet_amount_usd': bet_amount_usd,
        'bet_amount_currency': bet_amount_currency,
        'currency': currency,
        'rolls': rolls,
        'target': target,
        'chat_id': update.effective_chat.id,
        'chat_type': update.effective_chat.type,
        'command_message_id': update.message.message_id  # Store original command message ID for tagging
    }

    # Show mode selection with styled buttons
    normal_btn = apply_button_style(
        InlineKeyboardButton("Normal Mode (Highest wins)", callback_data=f"xdxw_mode_normal"),
        'primary', peb('normal')
    )
    crazy_btn = apply_button_style(
        InlineKeyboardButton("Crazy Mode (Lowest wins)", callback_data=f"xdxw_mode_crazy"),
        'danger', peb('crazy')
    )
    cancel_btn_xdxw = apply_button_style(
        InlineKeyboardButton("Cancel", callback_data="xdxw_cancel"),
        'danger', peb('cross')
    )
    keyboard = create_styled_keyboard([[normal_btn], [crazy_btn], [cancel_btn_xdxw]])

    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    sent_message = await update.message.reply_text(
        f"{pe(game_type)} <b>{game_type.upper()} Challenge Setup</b>\n\n"
        f"{pe('money')} Bet: {currency_symbol}{bet_amount_currency:.2f}\n"
        f"{pe('rolls')} Rolls per round: {rolls}\n"
        f"{pe('trophy')} Win condition: First to {target}\n\n"
        f"Select game mode:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    set_menu_owner(sent_message, user.id)

async def create_group_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    """Create a group PvP challenge with mode and rolls selection"""
    user = update.effective_user
    message_text = update.message.text.strip().split()

    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(message_text[1], user.id)
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /{} <amount>\nExample: /{} 5 or /{} all".format(game_type, game_type, game_type))
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    # Remember the original /dice <amount> command message id so the bot's
    # subsequent dice rolls can reply-tag the user (parity with /dice <amount>
    # XdX'w mode, which already does this). Without this, group-challenge PvB
    # bot rolls fall back to context.bot.send_dice(..., reply_to_message_id=None).
    context.user_data[f"gc_cmd_msg_{game_type}_{int(bet_amount_usd*100)}"] = update.message.message_id

    # Show mode and rolls selection with styled buttons
    gc_normal_btn = apply_button_style(
        InlineKeyboardButton("Normal Mode", callback_data=f"gc_mode_{game_type}_normal_{bet_amount_usd}_{bet_amount_currency}_{currency}"),
        'primary', peb('normal')
    )
    gc_crazy_btn = apply_button_style(
        InlineKeyboardButton("Crazy Mode", callback_data=f"gc_mode_{game_type}_crazy_{bet_amount_usd}_{bet_amount_currency}_{currency}"),
        'danger', peb('crazy')
    )
    keyboard = create_styled_keyboard([[gc_normal_btn], [gc_crazy_btn]])

    sent_message = await update.message.reply_text(
        f"{pe(game_type)} <b>Create {game_type.upper()} Challenge</b>\n\n"
        f"Select game mode:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    set_menu_owner(sent_message, user.id)

PLINKO_MULTIPLIERS = {
    "low": [16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1.0, 0.5, 1.0, 1.1, 1.2, 1.4, 1.4, 2, 9, 16],
    "medium": [110, 41, 10, 5, 3, 1.5, 1.0, 0.5, 0.3, 0.5, 1.0, 1.5, 3, 5, 10, 41, 110],
    "high": [1000, 130, 26, 9, 4, 2, 0.2, 0.2, 0.2, 0.2, 0.2, 2, 4, 9, 26, 130, 1000]
}

PLINKO_WEB_MULTIPLIERS = {
    8: {
        "low":    [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
        "medium": [13, 3, 1.3, 0.7, 0.4, 0.7, 1.3, 3, 13],
        "high":   [29, 4, 1.5, 0.3, 0.2, 0.3, 1.5, 4, 29]
    },
    10: {
        "low":    [8.9, 3, 1.4, 1.1, 1.0, 0.5, 1.0, 1.1, 1.4, 3, 8.9],
        "medium": [22, 5, 2, 1.4, 0.6, 0.4, 0.6, 1.4, 2, 5, 22],
        "high":   [76, 10, 3, 0.9, 0.3, 0.2, 0.3, 0.9, 3, 10, 76]
    },
    12: {
        "low":    [10, 3, 1.6, 1.4, 1.1, 1.0, 0.5, 1.0, 1.1, 1.4, 1.6, 3, 10],
        "medium": [33, 11, 4, 2, 1.1, 0.6, 0.3, 0.6, 1.1, 2, 4, 11, 33],
        "high":   [170, 24, 8.1, 2, 0.7, 0.2, 0.2, 0.2, 0.7, 2, 8.1, 24, 170]
    },
    14: {
        "low":    [7.1, 4, 1.9, 1.4, 1.3, 1.0, 1.0, 0.5, 1.0, 1.0, 1.3, 1.4, 1.9, 4, 7.1],
        "medium": [43, 13, 6, 3, 1.3, 1.0, 0.5, 0.3, 0.5, 1.0, 1.3, 3, 6, 13, 43],
        "high":   [284, 41, 10, 5, 2, 0.5, 0.2, 0.2, 0.2, 0.5, 2, 5, 10, 41, 284]
    },
    16: {
        "low":    [16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1.0, 0.5, 1.0, 1.1, 1.2, 1.4, 1.4, 2, 9, 16],
        "medium": [110, 41, 10, 5, 3, 1.5, 1.0, 0.5, 0.3, 0.5, 1.0, 1.5, 3, 5, 10, 41, 110],
        "high":   [1000, 130, 26, 9, 4, 2, 0.2, 0.2, 0.2, 0.2, 0.2, 2, 4, 9, 26, 130, 1000]
    }
}

PLINKO_WEB_ENABLED = True

PLINKO_WEB_PORT = 8086  # Separate port for plinko web dashboard

PLINKO_WEB_MAX_BET = 500.0

PLINKO_WEB_MIN_BET = 0.10

PLINKO_WEB_URL = "https://play-casino.app"  # Your HTTPS domain (Telegram requires HTTPS for Mini Apps)

PLINKO_AUTH_MAX_AGE_SECONDS = 3600    # Max age of initData before rejection (1 hour)

PLINKO_RATE_LIMIT_BETS_PER_MIN = 100  # Max bets per user per minute

PLINKO_MIN_BET_COOLDOWN_MS = 500     # Minimum 500ms between bets (prevents double-tap)

PLINKO_RATE_LIMIT_COOLDOWN_SEC = 1   # Show retry-after hint when rate limited

PLINKO_MAX_REQUEST_BODY_BYTES = 4096  # Max JSON body size for bet requests

_plinko_rate_limits: dict = {}  # {user_id: [timestamp, timestamp, ...]}

_plinko_last_bet_time: dict = {}  # {user_id: timestamp} - cooldown tracking

CHICKEN_ROAD_WEB_ENABLED    = True

CHICKEN_ROAD_WEB_PORT       = 8087

CHICKEN_ROAD_WEB_MAX_BET    = 200.0

CHICKEN_ROAD_WEB_MIN_BET    = 0.10

CHICKEN_ROAD_WEB_MAX_WIN    = 20000.0   # Hard cap on any single round payout

CHICKEN_ROAD_WEB_URL        = "https://play-casino.app"  # Same domain as Plinko

CHICKEN_ROAD_AUTH_MAX_AGE_SECONDS     = 3600

CHICKEN_ROAD_RATE_LIMIT_BETS_PER_MIN  = 20   # Max NEW GAMES per user per minute

CHICKEN_ROAD_MIN_BET_COOLDOWN_MS      = 1000  # 1s between game starts (not steps)

CHICKEN_ROAD_RATE_LIMIT_COOLDOWN_SEC  = 2

CHICKEN_ROAD_MAX_REQUEST_BODY_BYTES   = 8192  # Larger for step requests

CHICKEN_ROAD_MODES = {
    "easy": {
        "p_survive": 0.75,        # 3/4 safe columns (1 bone per row)
        "max_steps": 10,          # 10 rows
        "label": "Easy",
        "color": "#22c55e",
        "house_edge": 0.07,       # 7% house edge (consistent across all modes)
    },
    "medium": {
        "p_survive": 0.50,        # 2/4 safe columns (2 bones per row)
        "max_steps": 10,          # 10 rows
        "label": "Medium",
        "color": "#eab308",
        "house_edge": 0.07,       # 7% house edge
    },
    "hard": {
        "p_survive": 0.25,        # 1/4 safe columns (3 bones per row)
        "max_steps": 10,          # 10 rows
        "label": "Hard",
        "color": "#f97316",
        "house_edge": 0.07,       # 7% house edge
    },
}

CHICKEN_ROAD_HOUSE_EDGE = 0.07  # Default house edge (used only as fallback)

CHICKEN_ROAD_RTP = 1.0 - CHICKEN_ROAD_HOUSE_EDGE  # 0.93

_chicken_road_rate_limits:   dict = {}   # {user_id: [timestamp, ...]}

_chicken_road_last_bet_time: dict = {}   # {user_id: float}

_chicken_road_locks:         dict = {}   # {user_id: asyncio.Lock}

chicken_road_active_games:   dict = {}

def _build_chicken_road_mult_table() -> dict:
    table = {}
    for mode, cfg in CHICKEN_ROAD_MODES.items():
        p_survive  = cfg["p_survive"]
        max_steps  = cfg["max_steps"]
        house_edge = cfg.get("house_edge", CHICKEN_ROAD_HOUSE_EDGE)  # Use per-mode edge
        rtp        = 1.0 - house_edge
        table[mode] = []
        for n in range(1, max_steps + 1):
            survival_prob = p_survive ** n
            mult = rtp / survival_prob
            table[mode].append(round(mult, 2))
    return table

CHICKEN_ROAD_MULT_TABLE = _build_chicken_road_mult_table()

_chicken_road_html_cache: str | None = None

_chicken_road_html_cache_time: float = 0.0

WHEEL_SEGMENTS = [
    0.2, 0.5, 0.7, 1.0, 1.2, 1.5, 2.0, 0.5, 1.0, 1.5,
    2.5, 3.0, 0.7, 1.0, 1.5, 2.0, 3.5, 4.0, 1.0, 1.5,
    2.0, 2.5, 5.0, 1.0, 1.5, 2.0, 3.0, 7.0, 10.0, 1.5,
    2.0, 3.0, 5.0, 15.0, 2.0, 3.0, 5.0, 10.0, 20.0, 2.5,
    3.0, 5.0, 30.0, 3.0, 5.0, 10.0, 50.0, 1.0, 2.0, 5.0
]

SCRATCH_SYMBOLS = {
    "💎": {"mult": 100, "weight": 1},
    "👑": {"mult": 50, "weight": 2},
    "⭐": {"mult": 20, "weight": 5},
    "💰": {"mult": 10, "weight": 10},
    "🍀": {"mult": 5, "weight": 20},
    "🎰": {"mult": 2, "weight": 30},
    "❌": {"mult": 0, "weight": 50}
}

@check_banned
@check_maintenance
async def generic_emoji_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    if bot_stopped:
        await update.message.reply_text(f"{pe('cross')} Bot is currently stopped. No new matches can be started.")
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    message_text = update.message.text.strip().split()

    # New format: /dice @username amount MX ftY
    # M = N (normal) or C (crazy), X = 1, 2, or 3 (rolls)
    if len(message_text) != 5:
        await update.message.reply_text(
            f"<b>Usage:</b> <code>/{game_type} @username amount MX ftY</code>\n\n"
            f"<b>Parameters:</b>\n"
            f"• <code>@username</code> - Opponent's username\n"
            f"• <code>amount</code> - Bet amount (or 'all')\n"
            f"• <code>MX</code> - Mode and rolls:\n"
            f"  - <code>N1</code>, <code>N2</code>, <code>N3</code> - Normal mode (1-3 rolls)\n"
            f"  - <code>C1</code>, <code>C2</code>, <code>C3</code> - Crazy mode (1-3 rolls)\n"
            f"• <code>ftY</code> - First to Y points\n\n"
            f"<b>Examples:</b>\n"
            f"• <code>/{game_type} @player 10 N1 ft3</code>\n"
            f"• <code>/{game_type} @player 20 C2 ft5</code>",
            parse_mode=ParseMode.HTML
        )
        return

    opponent_username = normalize_username(message_text[1])
    amount_str = message_text[2].lower()
    mode_rolls_str = message_text[3].upper()
    ft_str = message_text[4].lower()

    if not opponent_username or opponent_username == normalize_username(user.username):
        await update.message.reply_text("Please specify a valid opponent's @username that is not yourself.")
        return

    # Parse mode and rolls (e.g., N1, C2, N3)
    if len(mode_rolls_str) != 2 or mode_rolls_str[0] not in ['N', 'C'] or mode_rolls_str[1] not in ['1', '2', '3']:
        await update.message.reply_text(
            "Invalid mode/rolls format. Use N1-N3 for Normal mode or C1-C3 for Crazy mode.\n"
            "Example: N1 (Normal, 1 roll), C2 (Crazy, 2 rolls)"
        )
        return

    game_mode = "normal" if mode_rolls_str[0] == 'N' else "crazy"
    game_rolls = int(mode_rolls_str[1])

    if amount_str == "all":
        bet_amount = get_active_balance_usd(user.id)
    else:
        try: bet_amount = float(amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return

    if not await check_bet_limits(update, bet_amount, f'pvp_{game_type}'):
        return

    if not ft_str.startswith("ft"):
        await update.message.reply_text("Invalid format for points target (must be ftX, e.g., ft3).")
        return
    try: target_points = int(ft_str[2:])
    except ValueError:
        await update.message.reply_text("Invalid points target.")
        return

    if get_active_balance_usd(user.id) < bet_amount:
        await send_insufficient_balance_message(update)
        return

    opponent_id = username_to_userid.get(opponent_username)
    if not opponent_id:
        try:
            chat = await context.bot.get_chat(opponent_username)
            opponent_id = chat.id
            await ensure_user_in_wallets(opponent_id, chat.username, context=context)
        except Exception:
            await update.message.reply_text(f"Opponent {opponent_username} not found. Ask them to DM the bot or send /bal first.")
            return

    await ensure_user_in_wallets(opponent_id, opponent_username, context=context)
    if get_active_balance_usd(opponent_id) < bet_amount:
        await update.message.reply_text(f"Opponent {opponent_username} does not have enough balance for this match.")
        return

    match_id = generate_unique_id("PVP")
    mode_text = "Highest total wins" if game_mode == "normal" else "Lowest total wins"
    match_data = {
        "id": match_id, "game_type": f"pvp_{game_type}", "bet_amount": bet_amount, "target_points": target_points,
        "points": {user.id: 0, opponent_id: 0}, "emoji_buffer": {},
        "players": [user.id, opponent_id],
        "usernames": {user.id: normalize_username(user.username) or f"ID{user.id}", opponent_id: opponent_username},
        "status": "pending", "last_roller": None,
        "host_id": user.id, "chat_id": update.effective_chat.id,
        "timestamp": str(datetime.now(timezone.utc)),
        "game_mode": game_mode,  # normal or crazy
        "game_rolls": game_rolls,  # 1, 2, or 3
        "player_rolls": {user.id: [], opponent_id: []},  # Track rolls for each player
        "round_timeout": default_round_timeout,  # Store timeout at creation time
    }
    game_sessions[match_id] = match_data
    # PERFORMANCE: Proactively index both players so subsequent dice
    # messages look up this match via O(user's games) instead of an
    # O(all sessions) full scan.
    _index_user_game(user.id, match_id)
    _index_user_game(opponent_id, match_id)
    accept_btn = apply_button_style(
        InlineKeyboardButton("Accept", callback_data=f"accept_{match_id}"),
        'success', peb('confirm')
    )
    decline_btn = apply_button_style(
        InlineKeyboardButton("Decline", callback_data=f"decline_{match_id}"),
        'danger', peb('cross')
    )
    keyboard_styled = create_styled_keyboard([[accept_btn, decline_btn]])

    sent_message = await update.message.reply_text(
        f"{pe('game')} <b>New {game_type.capitalize()} Match Request!</b>\n\n"
        f"{pe('user')} <b>Host:</b> {user.mention_html()}\n"
        f"{pe('target')} <b>Opponent:</b> {opponent_username}\n"
        f"{pe('money')} <b>Bet:</b> ${bet_amount:.2f}\n"
        f"{pe('normal') if game_mode == 'normal' else pe('crazy')} <b>Mode:</b> {game_mode.capitalize()} ({mode_text})\n"
        f"{pe('rolls')} <b>Rolls per round:</b> {game_rolls}\n"
        f"{pe('trophy')} <b>Target:</b> First to {target_points} points\n\n"
        f"{opponent_username}, tap {pe('confirm')} Accept to join!\n"
        f"\U0001f194 Match ID: <code>{match_id}</code>",
        reply_markup=keyboard_styled,
        parse_mode=ParseMode.HTML
    )

HISTORY_ITEMS_PER_PAGE = 10  # 5 in first row, 5 in second row

BSC_NODES = ["https://bsc-dataseed.binance.org/", "https://bsc-dataseed1.binance.org/"]

ETH_NODE = "https://linea-mainnet.infura.io/v3/25cdeb5b655744f2b6d88c998e55eace"

def get_working_web3_bsc():
    for node in BSC_NODES:
        try:
            w3 = Web3(Web3.HTTPProvider(node))
            if w3.is_connected():
                logging.info(f"Connected to BSC node: {node}")
                return w3
        except Exception as e:
            logging.warning(f"Failed to connect to BSC node {node}: {e}")
    logging.error("Could not connect to any BSC node")
    return None

try:
    w3_bsc = get_working_web3_bsc()
    w3_eth = Web3(Web3.HTTPProvider(ETH_NODE))
    if w3_bsc and w3_bsc.is_connected(): logging.info("Successfully connected to BSC")
    else: logging.error("Failed to connect to BSC")
    if w3_eth and w3_eth.is_connected(): logging.info("Successfully connected to ETH")
    else: logging.error("Failed to connect to ETH")
except Exception as e:
    logging.error(f"Failed to initialize Web3 connections: {e}")
    w3_bsc = w3_eth = None

ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"payable":true,"stateMutability":"payable","type":"fallback"},{"anonymous":false,"inputs":[{"indexed":true,"name":"owner","type":"address"},{"indexed":true,"name":"spender","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}]')

surprise_drops = {}  # {code: {amount, wager_requirement, claimed_by, claimed_by_username, timestamp, chat_id, message_id, status}}

surprise_drops_enabled = True  # Admin toggle

GAMES_HISTORY_PER_PAGE = 10

async def _event_loop_watchdog(application=None):
    """Watchdog task to confirm event loop is still running.

    PERFORMANCE: Ticks every 30s and only logs at DEBUG on the happy path.
    The old INFO-every-10s write caused noticeable log volume (+file I/O
    every 10s) that served no operational purpose once we know the loop is
    alive. WARNING logs still fire on anomalies (queue backlog, task
    explosions) which is what operators actually care about.

    The PTB application is passed in from ``post_init`` so we can inspect
    its update queue. The previous version referenced a bare ``app`` name
    which only existed as a local in ``main()``, so every queue-check tick
    raised ``NameError: name 'app' is not defined`` and got swallowed into
    a recurring ``[WATCHDOG] Error checking queue`` log line.
    """
    counter = 0
    last_task_count = 0
    while True:
        await asyncio.sleep(30)
        counter += 1
        task_count = len(asyncio.all_tasks())
        # Only warn on alarming conditions
        if task_count > 2000:
            logging.warning(
                f"[WATCHDOG] High active-task count: {task_count} (tick #{counter})"
            )
        elif task_count > last_task_count * 3 and task_count > 500:
            logging.warning(
                f"[WATCHDOG] Task count spiked: {last_task_count} -> {task_count}"
            )
        else:
            logging.debug(
                f"[WATCHDOG] alive tick={counter} tasks={task_count}"
            )
        last_task_count = task_count

        if application is None:
            continue
        try:
            update_queue = getattr(application, 'update_queue', None)
            if update_queue is not None and hasattr(update_queue, 'qsize'):
                qsize = update_queue.qsize()
                if qsize > 100:
                    logging.warning(
                        f"[WATCHDOG] Update queue backed up: {qsize} pending"
                    )
        except Exception as e:
            logging.error(f"[WATCHDOG] Error checking queue: {e}")

async def post_init(application: Application):
    """
    Post initialization hook to start background tasks.
    This runs after the event loop is started by run_polling().
    OPTIMIZED: Async data loading and all background tasks registered here.
    """
    # Note: the /tmp/post_init_called.txt debug breadcrumb was removed —
    # post_init is exercised on every startup and a blocking open()/write()
    # during startup was just noise, not a useful signal.
    logging.info("post_init starting...")
    
    # Start event loop watchdog (passes the PTB application so the
    # watchdog can inspect update_queue without relying on a module-level
    # ``app`` name that doesn't exist).
    application.create_task(_event_loop_watchdog(application))
    logging.info("Event loop watchdog started")
    
    # Initialize PostgreSQL pool and load data if enabled
    if USE_POSTGRES_FOR_ALL and pg_db:
        try:
            await pg_db.init_postgres_pool(POSTGRES_URL)
            await pg_db.load_all_users()
            
            # Sync PostgreSQL cache to global variables
            global user_wallets, username_to_userid, user_stats
            user_wallets = dict(pg_db._wallet_cache)
            username_to_userid = dict(pg_db._username_to_userid)
            user_stats = dict(pg_db._user_cache)
            
            logging.info(f"Loaded {len(user_stats)} users from PostgreSQL")
        except Exception as e:
            logging.error(f"Failed to initialize PostgreSQL: {e}", exc_info=True)
            raise
    
    try:
        # Start the on-demand deposit scanner (replaces global poll)
        application.create_task(active_scans_monitor_task(application))

        # Start the Plinko rate limit cleanup task
        application.create_task(plinko_rate_limit_cleanup_task(application))

        # Start the sweep task
        application.create_task(sweep_deposits_task(application))

        # Start the live price engine (MEXC API, every 5 minutes)
        application.create_task(update_live_prices())

        # Start the live fiat FX rates engine (USD -> INR/EUR/GBP, every 30 min)
        application.create_task(update_live_fiat_rates())

        # Start the raffle monitoring task
        application.create_task(monitor_raffles_task(application))

        # Start OxaPay webhook server
        application.create_task(start_oxapay_webhook_server(application))

        # Start Plinko web dashboard server with auto-restart
        application.create_task(start_plinko_web_server_with_restart(application))

        # Start Chicken Road rate limit cleanup task
        application.create_task(chicken_road_rate_limit_cleanup_task(application))

        # Start Chicken Road web game server with auto-restart
        application.create_task(start_chicken_road_web_server_with_restart(application))

        # Initialize deposit DB connection pool (if available)
        try:
            if 'deposit_db' in globals() and deposit_db and hasattr(deposit_db, '_init_pool'):
                await deposit_db._init_pool()
        except Exception as e:
            logging.warning(f"Could not initialize deposit pool: {e}")

        # Rebuild ban sets from loaded data
        _rebuild_ban_sets()
        logging.info(f"Ban sets: {len(_banned_set)} banned, {len(_tempbanned_set)} temp-banned")

        # Start all background tasks
        if USE_POSTGRES_FOR_ALL and pg_db:
            application.create_task(pg_db._flush_dirty_users())
            logging.info("PostgreSQL background flush task started")
        else:
            application.create_task(_flush_dirty_users())
        # Coalesced bot-state writer (replaces synchronous save_bot_state on
        # event loop — handlers just flip a dirty flag now).
        application.create_task(_flush_bot_state_loop())

        application.create_task(_cleanup_menu_owners())
        application.create_task(_cleanup_game_sessions())
        application.create_task(_cleanup_inflight_callbacks())
        application.create_task(_cleanup_rate_limit_timestamps())
        application.create_task(_cleanup_profile_pic_cache())

        # Jackpot: load persisted state, then start the daily-draw scheduler
        # and the periodic save loop. The scheduler sleeps until the next
        # 5:30 PM IST and runs the draw automatically.
        try:
            _jackpot_load()
        except Exception as e:
            logging.error(f"Failed to load jackpot state in post_init: {e}")
        application.create_task(_jackpot_scheduler_task(application))
        application.create_task(_jackpot_save_loop())
        logging.info("Jackpot scheduler + save loop started")

        # Register shutdown handler to save all data on stop
        # Note: add_shutdown_handler was removed in PTB 22.x
        # Shutdown is now handled via app.add_error_handler and context managers
        try:
            application.add_shutdown_handler(on_bot_shutdown)
        except AttributeError:
            # PTB 22.x doesn't have add_shutdown_handler
            # Register as error handler instead for graceful shutdown
            application.add_error_handler(
                lambda update, context: None,  # placeholder
            )
            logging.debug("Shutdown handler registration skipped (PTB 22.x)")

        logging.info("All systems initialized. Bot ready.")
    except Exception as e:
        logging.error(f"post_init failed: {e}", exc_info=True)
        raise

    logging.info("All systems initialized. Bot ready.")

async def on_bot_shutdown(application: Application):
    """Save all data when bot is shutting down."""
    logging.info("Bot shutdown handler triggered - saving all data...")
    try:
        # Use PostgreSQL save if enabled
        if USE_POSTGRES_FOR_ALL and pg_db:
            await pg_db.save_all_users()
            logging.info("PostgreSQL save complete")
        else:
            # Flush all dirty users first
            if _dirty_users:
                async with _dirty_lock:
                    batch = set(_dirty_users)
                loop = asyncio.get_running_loop()
                tasks = [
                    loop.run_in_executor(_save_executor, _sync_write_user, uid)
                    for uid in batch
                ]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logging.info(f"Flushed {len(batch)} dirty users to disk")
            # Save all remaining user data
            save_all_user_data()
        
        # Save all bot state (games, settings, escrow, etc.) + user files
        # defensively in case any dirtied-but-not-marked records slipped
        # through the flush.
        save_bot_state_full()
        # Persist jackpot state.
        try:
            _jackpot_save_now()
        except Exception as _e:
            logging.error(f"Failed to save jackpot state on shutdown: {_e}")
        logging.info("Bot shutdown save complete.")
    except Exception as e:
        logging.error(f"Error during bot shutdown: {e}", exc_info=True)

async def _cleanup_inflight_callbacks():
    """Periodically clear the inflight callback set and stale user action timestamps."""
    import time as _time_mod
    while True:
        await asyncio.sleep(60)
        # Clear inflight set - Telegram callback IDs expire in ~60s anyway
        async with _inflight_lock:
            _inflight_callbacks.clear()
        # Remove stale user action timestamps older than 10 minutes
        now = _time_mod.monotonic()
        for uid in list(_user_action_timestamps.keys()):
            ts_map = _user_action_timestamps[uid]
            stale = [k for k, v in ts_map.items() if now - v > 600]
            for k in stale:
                del ts_map[k]
            if not ts_map:
                del _user_action_timestamps[uid]

async def _cleanup_rate_limit_timestamps():
    """Clean stale entries from emoji_send_timestamps and _user_action_timestamps."""
    import time as _time_mod2
    while True:
        await asyncio.sleep(120)
        now = asyncio.get_event_loop().time()
        # Clean emoji_send_timestamps - entries older than 120s are stale
        stale_chats = [cid for cid, ts in list(emoji_send_timestamps.items()) if now - ts > 120]
        for cid in stale_chats:
            emoji_send_timestamps.pop(cid, None)

async def _cleanup_profile_pic_cache():
    """Evict expired entries from _profile_pic_cache every 10 minutes."""
    while True:
        await asyncio.sleep(600)
        now = datetime.now().timestamp()
        stale = [uid for uid, (img, ts) in list(_profile_pic_cache.items()) if now - ts > _PROFILE_PIC_CACHE_TTL * 2]
        for uid in stale:
            _profile_pic_cache.pop(uid, None)
        if stale:
            logging.debug(f"Profile pic cache: evicted {len(stale)} stale entries, {len(_profile_pic_cache)} remain")

async def _cleanup_menu_owners():
    """Remove expired menu ownership entries every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        now = datetime.now().timestamp()
        expired = [k for k, (_, exp) in list(_menu_owners.items()) if now > exp]
        for k in expired:
            _menu_owners.pop(k, None)
        if expired:
            logging.debug(f"Cleaned {len(expired)} expired menu owner entries")

async def _cleanup_game_sessions():
    """Remove stale/completed game sessions to prevent unbounded dict growth.
    PERFORMANCE: Runs every 5 minutes (was 15), more aggressive with completed sessions.
    Also cleans up stale wallet locks, game locks, and active games index."""
    while True:
        await asyncio.sleep(300)   # every 5 minutes (was 15)
        now = datetime.now(timezone.utc)
        to_delete = []
        for game_id, game in list(game_sessions.items()):
            status = game.get('status', 'unknown')
            try:
                ts = datetime.fromisoformat(
                    game.get('timestamp', '').replace('Z', '+00:00')
                )
                age_hours = (now - ts).total_seconds() / 3600
            except Exception:
                age_hours = 999

            if status == 'active' and age_hours > 2:
                to_delete.append(game_id)   # abandoned
            elif status in ('completed', 'cancelled', 'error', 'declined', 'cashout') and age_hours > 1:
                to_delete.append(game_id)   # was 24h, now 1h for completed
            elif status == 'pending' and age_hours > 0.167:   # 10 min
                to_delete.append(game_id)
            elif status.startswith('pending_') and age_hours > 0.5:  # 30 min for setup states
                to_delete.append(game_id)

        for game_id in to_delete:
            # Clean up game index entries
            game = game_sessions.get(game_id, {})
            for pid in game.get('players', []):
                _unindex_user_game(pid, game_id)
            if 'user_id' in game:
                _unindex_user_game(game['user_id'], game_id)
            # Clean up sidebet references — and ALSO purge the matching
            # active_sidebets records. Previously only match_sidebets was
            # cleared, leaving orphan entries in active_sidebets forever
            # (small but unbounded leak once games get abandoned).
            sb_ids = match_sidebets.pop(game_id, [])
            for _sb_id in sb_ids:
                active_sidebets.pop(_sb_id, None)
            # Remove from game locks
            _game_locks.pop(game_id, None)
            # Remove cashout button tracking
            _active_cashout_buttons.pop(game_id, None)
            _cashout_refresh_last.pop(game_id, None)
            # Remove session
            game_sessions.pop(game_id, None)

        # Clean up wallet locks for users with no active games (prevent
        # unbounded growth). PERFORMANCE: bumped batch cap from 200 -> 1000
        # so a 5000-user bot can actually drain the backlog within one cycle
        # instead of slowly bleeding forever.
        stale_lock_users = []
        for uid in list(_wallet_locks.keys()):
            if uid not in _user_active_games_index and uid not in active_pvb_games:
                stale_lock_users.append(uid)
        for uid in stale_lock_users[:1000]:
            lock = _wallet_locks.get(uid)
            if lock and not lock.locked():
                _wallet_locks.pop(uid, None)

        # Same story for withdrawal locks — they grow per-user and never shrink.
        for uid in list(_withdrawal_locks.keys())[:1000]:
            lock = _withdrawal_locks.get(uid)
            if lock and not lock.locked():
                _withdrawal_locks.pop(uid, None)

        # Clean up stale cashout buttons
        stale_co = [mid for mid, co in list(_active_cashout_buttons.items()) if mid not in game_sessions]
        for mid in stale_co:
            _active_cashout_buttons.pop(mid, None)
            _cashout_refresh_last.pop(mid, None)

        # Clean up active games index for stale entries
        for uid in list(_user_active_games_index.keys()):
            stale_ids = set()
            for gid in _user_active_games_index.get(uid, set()):
                if gid not in game_sessions or game_sessions[gid].get('status') not in ('active', 'pending', 'pending_reply_challenge', 'pending_setup', 'pending_pvb_setup'):
                    stale_ids.add(gid)
            for gid in stale_ids:
                _unindex_user_game(uid, gid)

        if to_delete:
            logging.info(f"Game session cleanup: removed {len(to_delete)} stale entries, {len(stale_lock_users)} stale locks")

SEVEN_UP_DOWN_2DICE = {
    "high":   {"range": (8, 12),  "multiplier": 2.23, "desc": "High (8-12)"},
    "low":    {"range": (2, 6),   "multiplier": 2.23, "desc": "Low (2-6)"},
    "7":      {"range": (7, 7),   "multiplier": 5.58, "desc": "7 (Exact 7)"},
    "odd":    {"check": "odd",    "multiplier": 1.92, "desc": "Odd"},
    "even":   {"check": "even",   "multiplier": 1.92, "desc": "Even"},
    "pair":   {"check": "pair",   "multiplier": 5.58, "desc": "Pair (Double)"},
    "low+":   {"range": (2, 4),   "multiplier": 5.58, "desc": "Low+ (2-4)"},
    "mid":    {"range": (5, 7),   "multiplier": 2.23, "desc": "Mid (5-7)"},
    "high-":  {"range": (8, 10),  "multiplier": 2.79, "desc": "High- (8-10)"},
    "high+":  {"range": (11, 12), "multiplier": 11.16, "desc": "High+ (11-12)"},
    "combo":  {"check": "combo16","multiplier": 16.74, "desc": "Combo (1,6)"},
}

SEVEN_UP_DOWN_3DICE = {
    "3low":    {"range": (3, 8),   "multiplier": 3.59, "desc": "3Low (3-8)"},
    "3mid":    {"range": (9, 12),  "multiplier": 1.93, "desc": "3Mid (9-12)"},
    "3high":   {"range": (13, 18), "multiplier": 3.59, "desc": "3High (13-18)"},
    "alldiff": {"check": "alldiff","multiplier": 1.67, "desc": "AllDiff (no repeat)"},
    "triple":  {"check": "triple", "multiplier": 33.48, "desc": "Triple (any)"},
    "allodd":  {"check": "allodd", "multiplier": 7.44, "desc": "AllOdd"},
    "alleven": {"check": "alleven","multiplier": 7.44, "desc": "AllEven"},
    "2kind":   {"check": "2kind",  "multiplier": 2.09, "desc": "2Kind (any pair)"},
    "seq3":    {"check": "seq3",   "multiplier": 8.37, "desc": "Seq3 (straight)"},
}

SEVEN_UP_3DICE_SPECIFIC = {
    "distinct_triple": 33.48,   # e.g., 1,2,3
    "pair_kicker":     66.96,   # e.g., 6,6,5
    "specific_triple": 200.88,  # e.g., 6,6,6
}

VALID_SEQUENCES_3DICE = [
    {1, 2, 3}, {2, 3, 4}, {3, 4, 5}, {4, 5, 6}
]

def _dice_sum_distribution(n_dice: int) -> dict:
    """Pre-compute probability distribution for sum of n dice (each 1-6).
    Returns {sum_value: probability}"""
    if n_dice == 1:
        return {i: 1/6 for i in range(1, 7)}
    elif n_dice == 2:
        dist = {}
        total = 36
        for i in range(1, 7):
            for j in range(1, 7):
                s = i + j
                dist[s] = dist.get(s, 0) + 1/total
        return dist
    elif n_dice == 3:
        dist = {}
        total = 216
        for i in range(1, 7):
            for j in range(1, 7):
                for k in range(1, 7):
                    s = i + j + k
                    dist[s] = dist.get(s, 0) + 1/total
        return dist
    return {}

_DICE_DIST = {n: _dice_sum_distribution(n) for n in [1, 2, 3]}

CASHOUT_HOUSE_EDGE = 0.07  # 7% house edge on cashouts

CASHOUT_BASE_MULTIPLIER = round(2 * (1 - CASHOUT_HOUSE_EDGE), 2)  # 1.86x fair payout * 0.5 = 0.93 at 50/50

_active_cashout_buttons: dict = {}

_cashout_refresh_last: dict = {}

_CASHOUT_REFRESH_MIN_INTERVAL = 1.0  # seconds

def _auto_start_services():
    """Auto-start required services (PostgreSQL, env setup) before bot launch.
    Called once at startup so that `python3 bot.py` brings everything up."""
    import subprocess
    import shutil

    # 1. Ensure PYTHONUNBUFFERED for real-time output
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    # 2. Try to start PostgreSQL if available and not already running
    pg_ctl = shutil.which("pg_ctlcluster") or shutil.which("pg_ctl")
    if pg_ctl:
        try:
            # Check if postgres is already running
            result = subprocess.run(
                ["pg_isready"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                print("[AUTO-START] PostgreSQL not running, attempting to start...")
                # Try systemctl first (systemd)
                systemctl = shutil.which("systemctl")
                if systemctl:
                    subprocess.run(
                        [systemctl, "start", "postgresql"],
                        capture_output=True, text=True, timeout=30
                    )
                else:
                    # Try service command
                    service = shutil.which("service")
                    if service:
                        subprocess.run(
                            [service, "postgresql", "start"],
                            capture_output=True, text=True, timeout=30
                        )
                    else:
                        # Direct pg_ctl
                        subprocess.run(
                            [pg_ctl, "start"], capture_output=True, text=True, timeout=30
                        )

                # Verify it started
                result2 = subprocess.run(
                    ["pg_isready"], capture_output=True, text=True, timeout=5
                )
                if result2.returncode == 0:
                    print("[AUTO-START] PostgreSQL started successfully")
                else:
                    print("[AUTO-START] WARNING: PostgreSQL may not have started properly")
            else:
                print("[AUTO-START] PostgreSQL already running")
        except FileNotFoundError:
            print("[AUTO-START] pg_isready not found - skipping PostgreSQL auto-start")
        except subprocess.TimeoutExpired:
            print("[AUTO-START] PostgreSQL start timed out")
        except Exception as e:
            print(f"[AUTO-START] PostgreSQL start failed: {e}")
    else:
        print("[AUTO-START] PostgreSQL tools not found - skipping auto-start")

    # 3. Ensure .env is loaded (already handled at top of file via load_dotenv)
    print("[AUTO-START] Environment variables loaded from .env")

    # 4. Create required directories
    for d in [LOGS_DIR, BASE_DIR]:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass

    print("[AUTO-START] Service initialization complete")

def main():
    # Auto-start all required services
    _auto_start_services()

    # Force logging configuration with unique log file per run
    log_filename = os.path.join(LOGS_DIR, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # PERFORMANCE: Non-blocking logging via QueueHandler + QueueListener so
    # disk I/O never blocks the asyncio event loop. A background thread drains
    # the queue into a size-capped RotatingFileHandler + stderr. Under 2000+
    # concurrent users the previous synchronous FileHandler was a real event-
    # loop staller — a slow disk flush during a noisy moment (e.g. the
    # watchdog ticking while 30 message handlers all log) would pause every
    # user's update for the duration of the fsync.
    import queue as _queue_mod
    from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

    root_logger = logging.getLogger()
    # Tear down any pre-existing config (basicConfig from imports, etc.)
    for _h in list(root_logger.handlers):
        try:
            root_logger.removeHandler(_h)
            _h.close()
        except Exception:
            pass

    _log_queue: _queue_mod.Queue = _queue_mod.Queue(-1)  # unbounded — never drop
    _log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Rotate at 50 MB, keep 5 backups (250 MB total cap) — prevents the log
    # file from growing without bound and chewing up disk on long-lived bots.
    _rotating_file_handler = RotatingFileHandler(
        log_filename, maxBytes=50 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    _rotating_file_handler.setFormatter(_log_formatter)
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(_log_formatter)

    _log_listener = QueueListener(
        _log_queue, _rotating_file_handler, _stream_handler,
        respect_handler_level=True
    )
    _log_listener.start()
    # Save a reference so atexit can flush it cleanly.
    globals()['_log_queue_listener'] = _log_listener

    _queue_handler = QueueHandler(_log_queue)
    root_logger.addHandler(_queue_handler)
    root_logger.setLevel(logging.INFO)

    # Mute noisy third-party INFO logging on the hot path (the bot's own
    # INFO logs stay intact). httpx logs every single request at INFO which
    # is massive once helper bots are rolling dice in parallel.
    for _noisy in ("httpx", "httpcore", "telegram.ext.Application",
                   "aiosqlite", "asyncio"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    logging.info(f"Log file: {log_filename}")
    logging.info("Starting bot...")

    # Load all language files at startup
    logging.info("Loading language files...")
    load_language_files()

    # ===== INITIALIZE DEPOSIT SYSTEM =====
    deposit_system_active = DEPOSIT_ENABLED
    if deposit_system_active:
        logging.info("Initializing deposit system...")
        # Validate configuration
        if not MASTER_MNEMONIC:
            logging.error("MASTER_MNEMONIC not set! Deposit system disabled.")
            deposit_system_active = False
        elif not HOT_WALLET_PRIVATE_KEY:
            logging.error("HOT_WALLET_PRIVATE_KEY not set! Deposit system disabled.")
            deposit_system_active = False
        elif not all(MASTER_WALLETS.values()):
            logging.warning("Not all master wallets configured. Some chains may not work.")

        if deposit_system_active:
            try:
                deposit_db = DepositDatabase()
                logging.info("Deposit database initialized successfully")
            except Exception as e:
                logging.error(f"Failed to initialize deposit database: {e}")
                logging.warning("Deposit system disabled due to initialization error")
                deposit_system_active = False

    if not PERPLEXITY_API_KEY or not PERPLEXITY_API_KEY.startswith("pplx-"):
        logging.warning("PERPLEXITY_API_KEY is not set correctly. Perplexity features will be disabled.")

    # Validate WIN_BROADCAST_CHANNEL_ID format
    if WIN_BROADCAST_CHANNEL_ID:
        # Check if it's a channel username (starts with @)
        if WIN_BROADCAST_CHANNEL_ID.startswith("@"):
            logging.info(f"Win broadcasting configured for public channel: {WIN_BROADCAST_CHANNEL_ID}")
        else:
            # Check if ID is a positive number without the -100 prefix
            try:
                channel_id_num = int(WIN_BROADCAST_CHANNEL_ID)
                if channel_id_num > 0:
                    logging.warning(f"{{pe('warning')}} WIN_BROADCAST_CHANNEL_ID ({WIN_BROADCAST_CHANNEL_ID}) is a positive number. "
                                  f"Channel IDs usually require a '-100' prefix (e.g., '-100{WIN_BROADCAST_CHANNEL_ID}'). "
                                  f"Broadcasting may fail if this format is incorrect.")
            except ValueError:
                logging.warning(f"{{pe('warning')}} WIN_BROADCAST_CHANNEL_ID ({WIN_BROADCAST_CHANNEL_ID}) is not a valid format. "
                              f"Use numeric ID (e.g., '-1003848853417') or channel username (e.g., '@mychannel').")

    if w3_bsc and w3_bsc.is_connected(): logging.info(f"BSC connected. Chain ID: {w3_bsc.eth.chain_id}")
    else: logging.warning("BSC connection failed")

    # PERFORMANCE: Tuned for 5000+ concurrent users.
    #   - concurrent_updates=512  → PTB dispatches up to 512 update tasks at
    #     once (was 256). For a pure-dice spike from a few thousand users
    #     we want headroom; anything past this gets queued, not dropped.
    #   - connection_pool_size=512 → HTTPX connection pool keeps enough hot
    #     sockets open for worst-case parallel outbound fan-out (broadcast,
    #     sidebet DM storms, raffle completion, admin broadcast).
    #   - PTB's AIORateLimiter (attached below) is what actually shapes
    #     traffic to Telegram; growing the pool doesn't break rate limits,
    #     it just prevents the pool from becoming a bottleneck when the
    #     rate limiter is willing to let us through.
    app_builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(512)
        .get_updates_pool_timeout(30)
        .get_updates_connect_timeout(15)
        .get_updates_read_timeout(15)
        .get_updates_write_timeout(15)
        .connection_pool_size(512)
        .pool_timeout(30)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
    )
    rate_limiter = create_optional_rate_limiter()
    if rate_limiter is not None:
        app_builder = app_builder.rate_limiter(rate_limiter)
    app = app_builder.build()
    # Conversation handlers
    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_set_house_balance$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_limits$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_set_daily_bonus$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_search_user$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_broadcast$"),
            CallbackQueryHandler(admin_gift_code_create_step1, pattern="^admin_gift_create$"),
        ],
        states={
            ADMIN_SET_HOUSE_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_house_balance_step)],
            ADMIN_LIMITS_CHOOSE_TYPE: [CallbackQueryHandler(admin_limits_choose_type_step, pattern="^admin_limit_type_")],
            ADMIN_LIMITS_CHOOSE_GAME: [CallbackQueryHandler(admin_limits_choose_game_step, pattern="^admin_limit_game_")],
            ADMIN_LIMITS_SET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_limits_set_amount_step)],
            ADMIN_SET_DAILY_BONUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_daily_bonus_step)],
            ADMIN_SEARCH_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_search_user_step)],
            ADMIN_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_step)],
            ADMIN_GIFT_CODE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_code_create_step2)],
            ADMIN_GIFT_CODE_CLAIMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_code_create_step3)],
            ADMIN_GIFT_CODE_WAGER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_code_create_step4)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_dashboard_command, pattern="^admin_dashboard$"),
            CallbackQueryHandler(admin_bot_settings_callback, pattern="^admin_bot_settings$"),
            CallbackQueryHandler(admin_gift_code_menu, pattern="^admin_gift_codes$"),
            # --- FIX STARTS HERE ---
            # Add a generic cancel handler that returns to the main admin dashboard
            # and properly ends the conversation. This will fix the stuck state issue.
            CallbackQueryHandler(admin_dashboard_command, pattern="^cancel_admin_action$"),
        ],
        # --- FIX ENDS HERE ---
        per_user=True,
        per_chat=True,
        conversation_timeout=timedelta(minutes=5).total_seconds(),
        block=False
    )

    game_setup_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_game_conversation, pattern="^game_mines_start$"),
            CommandHandler("mines", start_game_conversation_from_command),
            CommandHandler("m", start_game_conversation_from_command),  # Alias for /mines
        ],
        states={
            SELECT_BOMBS: [CallbackQueryHandler(select_bombs_callback, pattern="^bombs_")],
            SELECT_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_bet_amount_step)],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_conversation, pattern="^cancel_game$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=2).total_seconds(),
        block=False
    )

    tower_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(tower_ask_bet, pattern="^game_tower_start$"),
        ],
        states={
            TOWER_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tower_receive_bet)],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_conversation, pattern="^cancel_game$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=2).total_seconds(),
        block=False
    )

    pvb_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(pvb_menu_callback, pattern="^pvb_start_"),
            CallbackQueryHandler(pvb_menu_callback, pattern="^pvb_mode_"),
            CallbackQueryHandler(pvb_menu_callback, pattern="^pvb_rolls_"),
        ],
        states={
            SELECT_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pvb_get_bet_amount)],
            SELECT_TARGET_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pvb_get_target_score)],
            SELECT_WHO_ROLLS_FIRST: [CallbackQueryHandler(pvb_who_rolls_first_callback, pattern="^pvb_first_")],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_conversation, pattern="^cancel_game$")],
        per_message=False,
        per_chat=True,  # Explicitly set per_chat
        per_user=True,  # Explicitly set per_user
        conversation_timeout=timedelta(minutes=2).total_seconds(),
        block=False
    )
    ai_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ai_conversation, pattern="^main_ai$")],
        states={
            CHOOSE_AI_MODEL: [CallbackQueryHandler(choose_ai_model_callback)],
            ASK_AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_conversation_prompt)],
        },
        fallbacks=[CallbackQueryHandler(cancel_ai_conversation, pattern="^cancel_ai$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=5).total_seconds(),
        block=False
    )

    raffle_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(raffle_type_callback, pattern="^raffle_type_")],
        states={
            RAFFLE_PRIZE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_prize_step)],
            RAFFLE_TICKET_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_ticket_cost_step)],
            RAFFLE_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_duration_step)],
            RAFFLE_NUM_WINNERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, raffle_num_winners_step)],
        },
        fallbacks=[CallbackQueryHandler(raffle_cancel_callback, pattern="^raffle_cancel$")],
        per_user=True,
        conversation_timeout=timedelta(minutes=5).total_seconds(),
        block=False
    )

    recovery_handler = ConversationHandler(
        entry_points=[CommandHandler("recover", recover_command)],
        states={
            RECOVER_ASK_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recover_token_step)],
        },
        fallbacks=[CallbackQueryHandler(cancel_recovery_conversation, pattern="^cancel_recovery$")],
        per_user=True,
        conversation_timeout=timedelta(minutes=3).total_seconds(),
        block=False
    )

    withdrawal_address_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(settings_callback_handler, pattern="^settings_withdrawal$"),
            CallbackQueryHandler(withdrawal_change_callback, pattern="^settings_withdrawal_change$")
        ],
        states={
            SETTINGS_WITHDRAWAL_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_withdrawal_address_step)],
            SETTINGS_WITHDRAWAL_ADDRESS_CHANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_withdrawal_address_step)]
        },
        fallbacks=[CallbackQueryHandler(settings_command, pattern="^main_settings$")],
        per_user=True,
        conversation_timeout=timedelta(minutes=2).total_seconds(),
        block=False
    )

    withdrawal_flow_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(main_menu_callback, pattern="^main_withdraw$"),
            CallbackQueryHandler(withdraw_coin_callback, pattern="^withdraw_coin_"),
        ],
        states={
            WITHDRAWAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_withdrawal_amount)]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_withdrawal_conversation, pattern="^back_to_main$"),
            CommandHandler("cancel", cancel_withdrawal_conversation)
        ],
        per_user=True,
        conversation_timeout=timedelta(minutes=3).total_seconds(),
        allow_reentry=False,  # Prevent re-entry once conversation ends
        block=False
    )

    withdrawal_approval_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdrawal_approve_callback, pattern="^withdrawal_approve_")],
        states={
            WITHDRAWAL_APPROVAL_TXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdrawal_txid_step)]
        },
        fallbacks=[],
        per_user=True,
        conversation_timeout=timedelta(minutes=10).total_seconds(),
        block=False
    )


    # Auto-accept join requests for @playcsino group (chat_id: -1002240012522)
    async def auto_accept_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Automatically approve all chat join requests for @playcsino group."""
        join_request = update.chat_join_request
        if join_request and join_request.chat.id == -1002240012522:
            try:
                await join_request.approve()
                logging.info(f"Auto-approved join request from user {join_request.from_user.id} in @playcsino")
            except Exception as e:
                logging.error(f"Failed to approve join request from user {join_request.from_user.id}: {e}")

    app.add_handler(ChatJoinRequestHandler(chat_id=-1002240012522, callback=auto_accept_join_request))


    app.add_handler(CommandHandler("start", start_command, block=False))
    app.add_handler(CommandHandler("help", help_command, block=False))
    app.add_handler(CommandHandler(["bj", "blackjack"], blackjack_command, block=False))
    app.add_handler(CommandHandler("bjsplit", bjsplit_test_command, block=False))
    app.add_handler(CommandHandler("flip", coin_flip_command, block=False))
    app.add_handler(CommandHandler(["roul", "roulette"], roulette_command, block=False)); app.add_handler(CommandHandler("dr", dice_roll_command, block=False))
    # Dice Rush game commands
    app.add_handler(CommandHandler(["rush", "dicerush"], dice_rush_command, block=False))
    app.add_handler(CommandHandler(["rr", "rushrainbow"], rainbow_rush_command, block=False))
    app.add_handler(CommandHandler(["br", "blazerush"], blaze_rush_command, block=False))
    app.add_handler(CommandHandler("sl", slots_command, block=False)); app.add_handler(CommandHandler("bank", bank_command, block=False)); app.add_handler(CommandHandler("hb", bank_command, block=False)) # hb is alias for bank
    app.add_handler(CommandHandler("rain", rain_command, block=False)); app.add_handler(CommandHandler("stats", stats_command, block=False))
    app.add_handler(CommandHandler("jackpot", jackpot_command, block=False))  # Daily jackpot status / owner controls
    app.add_handler(CommandHandler("limits", limits_command, block=False)) # NEW - Game limits display
    app.add_handler(CommandHandler("users", users_command, block=False))
    # dice/darts/goal/bowl handlers are now registered via game_toggle_wrappers above
    app.add_handler(CommandHandler("clear", clear_command, block=False))
    app.add_handler(CommandHandler("timeout", timeout_command, block=False))
    app.add_handler(CommandHandler("clearall", clearall_command, block=False))
    app.add_handler(CommandHandler(["bal", "balance"], balance_command, block=False)); app.add_handler(CommandHandler("tip", tip_command, block=False))
    app.add_handler(CommandHandler("cashout", cashout_command, block=False)); app.add_handler(CommandHandler("cancel", cancel_command, block=False))
    app.add_handler(CommandHandler("stop", stop_command, block=False)); app.add_handler(CommandHandler("resume", resume_command, block=False))
    app.add_handler(CommandHandler("cancelall", cancel_all_command, block=False)); app.add_handler(CommandHandler("predict", predict_command, block=False))
    app.add_handler(CommandHandler("lb", limbo_command, block=False)); app.add_handler(CommandHandler("limbo", limbo_command, block=False)); app.add_handler(CommandHandler("Limbo", limbo_command, block=False)); app.add_handler(CommandHandler("keno", keno_command, block=False))
    app.add_handler(CommandHandler("hl", highlow_command, block=False))  # NEW: High-Low game
    app.add_handler(CommandHandler("matches", matches_command, block=False));
    app.add_handler(CommandHandler(["deals", "he"], deals_command, block=False))
    app.add_handler(CommandHandler("info", info_command, block=False))
    app.add_handler(CommandHandler("continue", continue_command, block=False))
    # New commands
    app.add_handler(CommandHandler("kick", kick_command, block=False)); app.add_handler(CommandHandler("promote", promote_command, block=False))
    app.add_handler(CommandHandler("pin", pin_command, block=False)); app.add_handler(CommandHandler("purge", purge_command, block=False))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command, block=False))
    app.add_handler(CommandHandler("referral", referral_command, block=False))
    app.add_handler(CommandHandler("setcode", setcode_command, block=False)) # NEW: Referral system
    app.add_handler(CommandHandler("code", code_command, block=False)) # NEW: Referral system
    app.add_handler(CommandHandler("raffle", raffle_command, block=False)) # NEW: Raffle system
    app.add_handler(CommandHandler("raffles", raffles_command, block=False)) # NEW: Raffle system
    app.add_handler(CommandHandler("info", info_command, block=False)) # NEW: Raffle system
    app.add_handler(CommandHandler("user", user_info_command, block=False))
    app.add_handler(CommandHandler("ai", ai_command, block=False))
    app.add_handler(CommandHandler("p", price_command, block=False))
    app.add_handler(CommandHandler("daily", daily_command, block=False))
    app.add_handler(CommandHandler("achievements", achievements_command, block=False))
    app.add_handler(CommandHandler("language", language_command, block=False))
    app.add_handler(CommandHandler(["currency", "cur"], currency_command, block=False))
    app.add_handler(CommandHandler(["maxbet", "limits"], maxbet_command, block=False))
    app.add_handler(CommandHandler("admin", admin_dashboard_command, block=False))
    app.add_handler(CommandHandler("gameshistory", games_history_command, block=False))
    app.add_handler(CommandHandler("admincommands", admin_commands_list, block=False))
    app.add_handler(CommandHandler("surprisedrop", surprisedrop_toggle_command, block=False))
    app.add_handler(CommandHandler("surprisedrop_now", surprisedrop_command, block=False))
    app.add_handler(CommandHandler("claim", claim_command, block=False))
    app.add_handler(CallbackQueryHandler(games_history_page_callback, pattern=r"^admin_ghist_page_", block=False))
    app.add_handler(CommandHandler("setbal", setbal_command, block=False))
    app.add_handler(CommandHandler("withdrawinfo", withdrawinfo_command, block=False))
    app.add_handler(CommandHandler("resetleaderboard", resetleaderboard_command, block=False))
    app.add_handler(CommandHandler("setdaily", setdaily_command, block=False)) # NEW
    app.add_handler(CommandHandler("dailyoff", dailyoff_command, block=False)) # NEW
    app.add_handler(CommandHandler("dailyon", dailyon_command, block=False)) # NEW
    # Game on/off toggle commands (admin only): /diceoff, /diceon, /minesoff, etc.
    for _gk3 in GAME_STATUS_MAP:
        async def _off_wrap(update, context, gk=_gk3):
            await game_off_command(update, context, gk)
        async def _on_wrap(update, context, gk=_gk3):
            await game_on_command(update, context, gk)
        app.add_handler(CommandHandler(f"{_gk3}off", _off_wrap, block=False))
        app.add_handler(CommandHandler(f"{_gk3}on", _on_wrap, block=False))
    # Add /tron and /troff aliases for tower
    async def _troff_wrap(update, context):
        await game_off_command(update, context, "tower")
    async def _tron_wrap(update, context):
        await game_on_command(update, context, "tower")
    app.add_handler(CommandHandler("troff", _troff_wrap, block=False))
    app.add_handler(CommandHandler("tron", _tron_wrap, block=False))
    # Add /moff and /mon aliases for mines
    async def _moff_wrap(update, context):
        await game_off_command(update, context, "mines")
    async def _mon_wrap(update, context):
        await game_on_command(update, context, "mines")
    app.add_handler(CommandHandler("moff", _moff_wrap, block=False))
    app.add_handler(CommandHandler("mon", _mon_wrap, block=False))
    app.add_handler(CommandHandler("gamestatus", game_status_command, block=False))
    app.add_handler(CommandHandler("aioff", ai_toggle_command, block=False)) # NEW: Toggle AI feature (using aioff/aion to avoid conflict with /ai command)
    # Game on/off toggle - separate commands: /diceoff, /diceon, etc.
    # Note: mines and tower are handled by their ConversationHandlers, not here
    _all_game_commands = {
        "dice": dice_command, "darts": darts_command, "goal": football_command, "bowl": bowling_command,
        "blackjack": blackjack_command, "coinflip": coin_flip_command, "roulette": roulette_command,
        "slots": slots_command, "keno": keno_command, "highlow": highlow_command,
        "limbo": limbo_command, "predict": predict_command, "crash": crash_command, "plinko": plinko_command,
        "wheel": wheel_command, "scratch": scratch_command, "coinchain": coinchain_command,
        "chicken_road": chicken_road_command,
    }
    for _gk2, _orig_h2 in _all_game_commands.items():
        async def _game_toggle_wrapper2(update, context, game_key=_gk2, orig=_orig_h2):
            if not is_game_enabled(game_key):
                await update.message.reply_text(
                    f"\U0001f527 <b>{game_key.title()}</b> game is currently under maintenance. "
                    f"Please try again later.",
                    parse_mode=ParseMode.HTML
                )
                return
            await orig(update, context)
        app.add_handler(CommandHandler(_gk2, _game_toggle_wrapper2, block=False))
    # Chicken Road aliases
    app.add_handler(CommandHandler(["cr", "chickenroad"], chicken_road_command, block=False))
    app.add_handler(CommandHandler("chicken", chicken_command, block=False))

    # /dart alias for /darts
    async def _dart_alias(update, context):
        if not is_game_enabled("darts"):
            await update.message.reply_text(
                f"\U0001f527 <b>Darts</b> game is currently under maintenance. Please try again later.",
                parse_mode=ParseMode.HTML
            )
            return
        await darts_command(update, context)
    app.add_handler(CommandHandler("dart", _dart_alias, block=False))

    # 7Up7Down game handler
    app.add_handler(CommandHandler(["7up", "7updown", "7ud"], seven_up_command, block=False))

    # Side Bets handlers
    app.add_handler(CommandHandler(["sidebets", "sides"], sidebets_command, block=False))
    app.add_handler(CommandHandler("win", win_bet_command, block=False))
    app.add_handler(CommandHandler("lose", lose_bet_command, block=False))

    # Reply-to-message PvP challenge callback handlers
    app.add_handler(CallbackQueryHandler(rpvp_confirm_callback, pattern=r"^rpvp_confirm_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_playbot_callback, pattern=r"^rpvp_playbot_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_cancel_callback, pattern=r"^rpvp_cancel_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_mode_callback, pattern=r"^rpvp_mode_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_rolls_callback, pattern=r"^rpvp_rolls_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_target_callback, pattern=r"^rpvp_target_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_mode_callback, pattern=r"^rpvp_pvb_mode_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_rolls_callback, pattern=r"^rpvp_pvb_rolls_", block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_target_callback, pattern=r"^rpvp_pvb_target_", block=False))

    # Callback handler for game_cr in games menu
    app.add_handler(CallbackQueryHandler(
        game_chicken_road_callback,
        pattern=r"^game_cr$",
        block=False
    ))
    app.add_handler(CommandHandler("games", games_menu, block=False)) # New alias
    app.add_handler(CommandHandler("tower", tower_command, block=False)) # NEW - Tower game
    app.add_handler(CommandHandler("tr", tower_command, block=False)) # NEW - Tower game alias
    app.add_handler(CommandHandler("active", active_games_command, block=False)) # NEW
    app.add_handler(CommandHandler("activeall", active_all_games_command, block=False)) # NEW
    app.add_handler(CommandHandler("reset", reset_recovery_command, block=False)) # NEW
    app.add_handler(CommandHandler("export", export_command, block=False)) # NEW
    app.add_handler(CommandHandler("claim", claim_gift_code_command, block=False)) # NEW
    # History command for users (with template image and pagination)
    app.add_handler(CommandHandler(["history", "hc"], history_command, block=False))
    app.add_handler(CommandHandler("leaderboardrf", leaderboard_referral_command, block=False)) # NEW
    app.add_handler(CommandHandler("weekly", weekly_bonus_command, block=False)) # NEW
    app.add_handler(CommandHandler("monthly", monthly_bonus_command, block=False)) # NEW
    app.add_handler(CommandHandler("demo", demo_command, block=False)) # NEW: Demo claim system
    app.add_handler(CommandHandler(["transactions", "tx"], transactions_command, block=False))
    app.add_handler(CommandHandler("transaction", transactions_command, block=False)) # Admin version
    app.add_handler(CommandHandler("serverseed", serverseed_command, block=False)) # NEW: Provably fair
    app.add_handler(CommandHandler("seed", seed_command, block=False)) # NEW: Provably fair
    app.add_handler(CommandHandler("rk", rakeback_command, block=False)) # NEW
    app.add_handler(CommandHandler("level", level_command, block=False)) # NEW
    app.add_handler(CommandHandler("levelall", level_all_command, block=False)) # NEW
    # REMOVED NEW GAMES: crash, plinko, wheel, scratch, coinchain
    # New Group Management Commands
    app.add_handler(CommandHandler("mute", mute_command, block=False))
    app.add_handler(CommandHandler("report", report_command, block=False))
    app.add_handler(CommandHandler("translate", translate_command, block=False))
    app.add_handler(CommandHandler("lockall", lockall_command, block=False))
    app.add_handler(CommandHandler("unlockall", unlockall_command, block=False))

    # ===== DEPOSIT SYSTEM HANDLERS =====
    app.add_handler(CommandHandler("deposit", deposit_command, block=False))
    app.add_handler(CallbackQueryHandler(deposit_method_callback, pattern=r"^deposit_(ETH|BNB|BASE|TRON|SOLANA|TON)$", block=False))
    app.add_handler(CallbackQueryHandler(check_deposit_status, pattern=r"^(deposit_history|check_deposit_)", block=False))
    app.add_handler(CallbackQueryHandler(back_to_deposit_menu, pattern=r"^back_to_deposit_menu", block=False))

    # OxaPay ConversationHandler
    oxapay_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(oxapay_deposit_start, pattern=r"^deposit_oxapay$")],
        states={
            OXAPAY_ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, oxapay_receive_amount)],
            OXAPAY_ASK_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, oxapay_receive_currency)],
        },
        fallbacks=[CommandHandler("cancel", oxapay_cancel)],
        per_user=True,
        conversation_timeout=timedelta(minutes=5).total_seconds(),
        block=False
    )
    app.add_handler(oxapay_handler)

    # ===== RAIN SYSTEM HANDLERS =====
    app.add_handler(CallbackQueryHandler(join_rain_callback, pattern=r"^join_rain_", block=False))

    # REMOVED bonus_callback_handler as it's no longer in the main menu
    app.add_handler(admin_handler)
    app.add_handler(game_setup_handler)
    app.add_handler(tower_handler)  # NEW - Tower game conversation
    app.add_handler(pvb_handler)
    # ai_handler removed - AI feature disabled
    app.add_handler(raffle_handler)  # NEW - Raffle creation conversation
    app.add_handler(recovery_handler)
    app.add_handler(withdrawal_address_handler)
    app.add_handler(withdrawal_flow_handler)
    app.add_handler(withdrawal_approval_handler)

    # OPTIMIZED: Register most frequently used callback handlers FIRST
    # This reduces handler lookup time since PTB checks handlers in order

    # NEW: Emoji game setup callback handler (before main_menu_callback)
    app.add_handler(CallbackQueryHandler(emoji_game_setup_callback, pattern=r"^egsetup_", block=False))

    # 1. Main menu handler (MOST USED - handles balance, wallet, settings, bonuses, etc.)
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^(main_|back_to_main|deposit_usdt_menu|deposit_coming_soon|my_matches_|my_deals_|my_history_|my_transactions)", block=False))

    # 2. Game category and play handlers (high frequency)
    app.add_handler(CallbackQueryHandler(games_category_callback, pattern=r"^games_(category_|emoji_)", block=False))
    app.add_handler(CallbackQueryHandler(play_single_emoji_callback, pattern=r"^play_single_", block=False))

    # 3. Tip and withdrawal handlers (common user actions)
    app.add_handler(CallbackQueryHandler(tip_confirm_callback, pattern=r"^(confirm_tip_|cancel_tip_)", block=False))
    app.add_handler(CallbackQueryHandler(withdraw_coin_callback, pattern=r"^withdraw_coin_", block=False))

    # 4. Group challenge handlers
    app.add_handler(CallbackQueryHandler(group_challenge_mode_callback, pattern=r"^gc_mode_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_rolls_callback, pattern=r"^gc_rolls_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_target_callback, pattern=r"^gc_target_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_accept_callback, pattern=r"^gc_accept_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_playbot_callback, pattern=r"^gc_playbot_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_cancel_callback, pattern=r"^gc_cancel_", block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_botfirst_callback, pattern=r"^gc_botfirst_", block=False))

    # PvB Cashout handler
    app.add_handler(CallbackQueryHandler(pvb_cashout_callback, pattern=r"^pvb_cashout_", block=False))

    # 5. XdXw handlers
    app.add_handler(CallbackQueryHandler(xdxw_mode_callback, pattern=r"^xdxw_mode_|^xdxw_cancel$", block=False))
    app.add_handler(CallbackQueryHandler(xdxw_accept_callback, pattern=r"^xdxw_accept_", block=False))
    app.add_handler(CallbackQueryHandler(xdxw_playbot_callback, pattern=r"^xdxw_playbot_", block=False))
    app.add_handler(CallbackQueryHandler(xdxw_bot_first_callback, pattern=r"^xdxw_bot_first_", block=False))
    app.add_handler(CallbackQueryHandler(xdxw_cancel_match_callback, pattern=r"^xdxw_cancel_", block=False))

    # 6. Rebet/Double button handlers (MUST be before general game handlers)
    app.add_handler(CallbackQueryHandler(slots_rebet_double_callback, pattern=r"^slots_(rebet|double)_", block=False))
    app.add_handler(CallbackQueryHandler(coinflip_rebet_double_callback, pattern=r"^coinflip_(rebet|double)_", block=False))
    app.add_handler(CallbackQueryHandler(highlow_rebet_double_callback, pattern=r"^highlow_(rebet|double)_", block=False))
    app.add_handler(CallbackQueryHandler(keno_rebet_double_callback, pattern=r"^keno_(rebet|double)_", block=False))
    app.add_handler(CallbackQueryHandler(mines_rebet_double_callback, pattern=r"^mines_(rebet|double)_", block=False))
    app.add_handler(CallbackQueryHandler(tower_rebet_double_callback, pattern=r"^tower_(rebet|double)_", block=False))

    # 7. General game callback handlers
    app.add_handler(CallbackQueryHandler(coin_flip_callback, pattern=r"^flip_", block=False))
    app.add_handler(CallbackQueryHandler(tower_callback, pattern=r"^tower_", block=False))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern=r"^roul_", block=False))
    app.add_handler(CallbackQueryHandler(highlow_callback, pattern=r"^hl_", block=False))
    app.add_handler(CallbackQueryHandler(keno_callback, pattern=r"^keno_", block=False))
    app.add_handler(CallbackQueryHandler(coinchain_callback, pattern=r"^coinchain_", block=False))
    app.add_handler(CallbackQueryHandler(mines_pick_callback, pattern=r"^mines_", block=False))
    app.add_handler(CallbackQueryHandler(blackjack_callback, pattern=r"^bj_", block=False))
    app.add_handler(CallbackQueryHandler(game_info_callback, pattern=r"^game_", block=False))
    # Help buttons for Mines and Tower
    app.add_handler(CallbackQueryHandler(game_help_callback, pattern=r"^(mines_help|tower_help)$", block=False))
    # History pagination and view callbacks
    app.add_handler(CallbackQueryHandler(history_page_callback, pattern=r"^hist_page_", block=False))
    app.add_handler(CallbackQueryHandler(history_view_callback, pattern=r"^hist_view_", block=False))
    app.add_handler(CallbackQueryHandler(transactions_page_callback, pattern=r"^txn_page_", block=False))
    app.add_handler(CallbackQueryHandler(transactions_close_callback, pattern=r"^txn_close_", block=False))
    app.add_handler(CallbackQueryHandler(close_callback, pattern=r"^close$", block=False))
    app.add_handler(CallbackQueryHandler(clear_confirm_callback, pattern=r"^(clear|clearall)_confirm_", block=False))
    app.add_handler(CallbackQueryHandler(match_invite_callback, pattern=r"^(accept_|decline_)", block=False))
    app.add_handler(CallbackQueryHandler(stop_confirm_callback, pattern=r"^stop_confirm_", block=False))
    app.add_handler(CallbackQueryHandler(pvb_menu_callback, pattern="^pvp_info_", block=False))

    # 8. User settings and info handlers
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings_", block=False))
    app.add_handler(CallbackQueryHandler(currency_callback, pattern=r"^(setcurrency_|setdisplay_|noop_cur_header)", block=False))
    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_", block=False))
    app.add_handler(CallbackQueryHandler(stats_view_callback, pattern=r"^stats_(24h|alltime)_", block=False))
    app.add_handler(CallbackQueryHandler(users_navigation_callback, pattern=r"^users_", block=False))
    app.add_handler(CallbackQueryHandler(price_update_callback, pattern=r"^price_update_", block=False))

    # Escrow handler removed

    # 10. Raffle system handlers
    app.add_handler(CallbackQueryHandler(raffles_mine_callback, pattern=r"^raffles_mine_", block=False))
    app.add_handler(CallbackQueryHandler(raffles_active_callback, pattern=r"^raffles_active", block=False))
    app.add_handler(CallbackQueryHandler(raffles_back_callback, pattern=r"^raffles_back", block=False))

    # 11. Referral handlers
    app.add_handler(CallbackQueryHandler(referral_transfer_callback, pattern=r"^ref_transfer_", block=False))
    app.add_handler(CallbackQueryHandler(referral_check_callback, pattern=r"^ref_check_", block=False))

    # 12. Leaderboard handlers
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern=r"^leaderboard_(weekly|monthly|wins|alltime)_", block=False))

    # 13. Level pagination
    app.add_handler(CallbackQueryHandler(level_all_command, pattern=r"^levels_", block=False))

    # 14. Active games navigation
    app.add_handler(CallbackQueryHandler(active_all_navigation_callback, pattern=r"^activeall_", block=False))

    # 15. Admin handlers (rarely used, put last)
    app.add_handler(CallbackQueryHandler(admin_actions_callback, pattern=r"^admin_(dashboard|users|bot_settings|toggle_maintenance|broadcast|set_house_balance|limits|gift_codes|toggle_withdrawals|pending_withdrawals|active_games|export_data)$", block=False))
    app.add_handler(CallbackQueryHandler(admin_user_search_callback, pattern=r"^admin_user_", block=False))

    # 16. Withdrawal cancellation
    app.add_handler(CallbackQueryHandler(withdrawal_cancel_callback, pattern=r"^withdrawal_cancel_", block=False))

    # CRITICAL: Single emoji bet handler MUST be first to catch bet input before any other handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, single_emoji_bet_handler, block=False))

    # Bonus adjustment system handlers
    app.add_handler(CallbackQueryHandler(bonus_adjust_callback, pattern=r"^bonus_adjust_", block=False))
    app.add_handler(CallbackQueryHandler(bonus_notify_callback, pattern=r"^bonus_notify_", block=False))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bonus_percentage_input, block=False))

    # Provably Fair Callbacks (OLD SYSTEM - REMOVED, now using deep links to DM)
    # app.add_handler(CallbackQueryHandler(pf_rotate_seeds_callback, pattern=r"^pf_rotate_seeds$"))
    # app.add_handler(CallbackQueryHandler(pf_show_game_details_callback, pattern=r"^pf_show_"))
    # app.add_handler(CallbackQueryHandler(pf_verify_menu_callback, pattern=r"^pf_verify_menu$"))

    # Verification game handlers (OLD SYSTEM - REMOVED)
    # app.add_handler(CallbackQueryHandler(pf_verify_coinflip_callback, pattern=r"^pf_verify_coinflip$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_roulette_callback, pattern=r"^pf_verify_roulette$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_highlow_callback, pattern=r"^pf_verify_highlow$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_blackjack_callback, pattern=r"^pf_verify_blackjack$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_keno_callback, pattern=r"^pf_verify_keno$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_mines_callback, pattern=r"^pf_verify_mines$"))
    # app.add_handler(CallbackQueryHandler(pf_verify_tower_callback, pattern=r"^pf_verify_tower$"))

    # Provably Fair Conversation Handler for seed changes (KEEPING - used by /seed command)
    pf_seed_change_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(pf_change_client_seed_callback, pattern=r"^pf_change_client_seed$")],
        states={
            PF_CHANGE_CLIENT_SEED_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pf_client_seed_input_handler),
                CallbackQueryHandler(pf_cancel_seed_change_callback, pattern=r"^pf_cancel_seed_change$")
            ]
        },
        fallbacks=[CommandHandler("cancel", pf_cancel_handler)],
        per_user=True,
        per_chat=True,
        conversation_timeout=timedelta(minutes=5).total_seconds(),
        block=False
    )
    app.add_handler(pf_seed_change_handler)

    # Provably Fair Verification ConversationHandler (OLD SYSTEM - REMOVED)
    # pf_verification_handler = ConversationHandler(
    #     entry_points=[
    #         CallbackQueryHandler(pf_verify_coinflip_callback, pattern=r"^pf_verify_coinflip$"),
    #         CallbackQueryHandler(pf_verify_roulette_callback, pattern=r"^pf_verify_roulette$"),
    #         CallbackQueryHandler(pf_verify_highlow_callback, pattern=r"^pf_verify_highlow$"),
    #         CallbackQueryHandler(pf_verify_blackjack_callback, pattern=r"^pf_verify_blackjack$"),
    #         CallbackQueryHandler(pf_verify_keno_callback, pattern=r"^pf_verify_keno$"),
    #         CallbackQueryHandler(pf_verify_mines_callback, pattern=r"^pf_verify_mines$"),
    #         CallbackQueryHandler(pf_verify_tower_callback, pattern=r"^pf_verify_tower$")
    #     ],
    #     states={
    #         PF_VERIFY_INPUT_SERVER_SEED: [
    #             MessageHandler(filters.TEXT & ~filters.COMMAND, pf_verify_server_seed_input),
    #             CallbackQueryHandler(pf_verify_cancel_callback, pattern=r"^pf_verify_cancel$")
    #         ],
    #         PF_VERIFY_INPUT_CLIENT_SEED: [
    #             MessageHandler(filters.TEXT & ~filters.COMMAND, pf_verify_client_seed_input),
    #             CallbackQueryHandler(pf_verify_cancel_callback, pattern=r"^pf_verify_cancel$")
    #         ],
    #         PF_VERIFY_INPUT_NONCE: [
    #             MessageHandler(filters.TEXT & ~filters.COMMAND, pf_verify_nonce_input),
    #             CallbackQueryHandler(pf_verify_cancel_callback, pattern=r"^pf_verify_cancel$")
    #         ],
    #         PF_VERIFY_INPUT_PARAM: [
    #             MessageHandler(filters.TEXT & ~filters.COMMAND, pf_verify_param_input),
    #             CallbackQueryHandler(pf_verify_param_callback, pattern=r"^pf_verify_param_"),
    #             CallbackQueryHandler(pf_verify_cancel_callback, pattern=r"^pf_verify_cancel$")
    #         ]
    #     },
    #     fallbacks=[CallbackQueryHandler(pf_verify_cancel_callback, pattern=r"^pf_verify_cancel$")],
    #     per_user=True,
    #     per_chat=False,  # Changed to False so it works across chats (groups → DM)
    #     conversation_timeout=timedelta(minutes=10).total_seconds()
    # )
    # app.add_handler(pf_verification_handler)


    # Message listener for text and dice emojis
    app.add_handler(MessageHandler(filters.Dice.ALL | (filters.TEXT & ~filters.COMMAND), message_listener, block=False))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, message_listener, block=False)) # For welcome message

    # Global error handler to catch and log all unhandled exceptions
    async def error_handler(update, context):
        logging.error("Exception in handler:", exc_info=context.error)
        if update and hasattr(update, 'message') and update.message:
            try:
                await update.message.reply_text(f"{pe('cross')} An error occurred. Please try again.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
        elif update and hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.answer(f"{pe('cross')} An error occurred. Please try again.", show_alert=True)
            except Exception:
                pass
    app.add_error_handler(error_handler)

    if app.job_queue:

        for deal_id, deal in escrow_deals.items():
            if deal.get("status") == "accepted_awaiting_deposit":
                logging.info(f"Recovered active escrow deal {deal_id}, restarting monitor.")
                app.job_queue.run_repeating(monitor_escrow_deposit, interval=20, first=10, data={'deal_id': deal_id}, name=f"escrow_monitor_{deal_id}")

        # NEW: Schedule bonus notification checks (run every 30 minutes)
        app.job_queue.run_repeating(check_and_send_bonus_notifications, interval=1800, first=60)
        logging.info("Scheduled bonus notification checker")

        # Start live price engine as background task
        async def _price_update_job(context):
            """Wrapper to run price update once via job_queue."""
            global LIVE_PRICES
            symbols_map = {
                "ETHUSDT": "ETH", "BNBUSDT": "BNB", "SOLUSDT": "SOL",
                "TRXUSDT": "TRX", "LTCUSDT": "LTC", "BTCUSDT": "BTC",
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("https://api.mexc.com/api/v3/ticker/price")
                    if resp.status_code == 200:
                        data = resp.json()
                        price_map = {item["symbol"]: float(item["price"]) for item in data}
                        for api_sym, coin in symbols_map.items():
                            if api_sym in price_map and price_map[api_sym] > 0:
                                LIVE_PRICES[coin] = price_map[api_sym]
                        LIVE_PRICES["USDT"] = 1.0
                        logging.info(f"Live prices updated via job_queue")
            except Exception as e:
                logging.warning(f"Failed to fetch live prices: {e}")

        app.job_queue.run_repeating(_price_update_job, interval=300, first=5)  # Every 5 min
        logging.info("Scheduled live price update task")

        # ===== DEPOSIT SYSTEM BACKGROUND TASKS =====
        if deposit_system_active:
            logging.info("Starting deposit monitoring tasks...")


    else:
        logging.warning("Job queue not available.")

    # ===== HELPER BOT APPLICATION SETUP =====
    # Set up helper bot with callback handlers for group messages
    if helper_bot and HELPER_BOT_TOKEN:
        try:
            # PERFORMANCE: helper_app also needs real headroom — the previous
            # 15/15 pool would starve the moment multiple groups were
            # generating leaderboard/price callbacks simultaneously.
            helper_app = (
                ApplicationBuilder()
                .token(HELPER_BOT_TOKEN)
                .concurrent_updates(128)
                .connection_pool_size(128)
                .pool_timeout(20)
                .connect_timeout(10)
                .read_timeout(20)
                .write_timeout(20)
                .build()
            )

            # Register only callback handlers that helper bot needs for its messages
            helper_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern=r"^leaderboard_(weekly|monthly|wins|alltime)_", block=False))
            helper_app.add_handler(CallbackQueryHandler(stats_view_callback, pattern=r"^stats_(24h|alltime)_", block=False))
            helper_app.add_handler(CallbackQueryHandler(price_update_callback, pattern=r"^price_update_", block=False))

            logging.info("Helper bot application initialized with callback handlers")
        except Exception as e:
            logging.warning(f"Failed to initialize helper bot application: {e}")
            helper_app = None

    print("Bot started successfully with all new features!")
    print("Press Ctrl+C to stop.")

    # Run both main and helper bot applications concurrently
    if helper_app:
        async def run_bots():
            """Run both main and helper bot applications concurrently.

            Ctrl+C handling: We deliberately replace the module-level
            ``signal.signal(SIGINT, _signal_handler)`` with a loop-aware
            ``add_signal_handler`` here. The module-level sync handler just
            sets ``bot_stopped`` and returns — it never raises, so Python
            never converts SIGINT into a KeyboardInterrupt that the
            ``await stop_event.wait()`` could observe. In the
            ``app.run_polling()`` branch PTB installs its own loop-aware
            handler so this isn't an issue, but in the helper_app branch we
            drive the event loop manually and have to do it ourselves —
            otherwise Ctrl+C just logs "saving data" and the bot keeps
            polling.
            """
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def _request_stop(signum):
                # Idempotent. Loop-thread safe (called from the loop's signal
                # handler dispatcher, not from a signal context).
                if not stop_event.is_set():
                    logging.info(
                        f"Received signal {signum}, initiating graceful shutdown..."
                    )
                    global bot_stopped
                    bot_stopped = True
                    stop_event.set()

            try:
                for _sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.add_signal_handler(_sig, _request_stop, _sig)
                    except NotImplementedError:
                        # Windows / restricted environments — fall back to
                        # signal.signal which at least sets the flag.
                        pass
            except Exception as _sig_e:
                logging.warning(
                    f"Could not install loop signal handlers: {_sig_e}"
                )

            try:
                await app.initialize()
                await app.start()
                await post_init(app)
                # drop_pending_updates avoids a restart causing a thundering-
                # herd replay of every update queued while the bot was down.
                await app.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )

                await helper_app.initialize()
                await helper_app.start()
                await helper_app.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )

                # Keep both running until SIGINT/SIGTERM sets the event.
                # The earlier `except KeyboardInterrupt` clause around this
                # await never actually fired — KeyboardInterrupt is raised
                # at the bottom of asyncio.run, not inside the awaiting
                # coroutine, so the explicit signal handler above is what
                # makes Ctrl+C stop the bot in this branch.
                await stop_event.wait()
            except (KeyboardInterrupt, SystemExit):
                pass
            except Exception as e:
                logging.critical(f"Bot runtime error: {e}", exc_info=True)
            finally:
                # Shutdown helper bot
                try:
                    if helper_app.updater.running:
                        await helper_app.updater.stop()
                    await helper_app.stop()
                    await helper_app.shutdown()
                except Exception as e:
                    logging.warning(f"Helper app shutdown error: {e}")

                # Shutdown main bot
                try:
                    if app.updater.running:
                        await app.updater.stop()
                    await app.stop()
                    await app.shutdown()
                except Exception as e:
                    logging.warning(f"Main app shutdown error: {e}")

                # Drop the loop signal handlers so the second Ctrl+C (or any
                # late-arriving SIGTERM) gets the interpreter's default
                # behaviour and we don't end up wedged here.
                for _sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.remove_signal_handler(_sig)
                    except (NotImplementedError, ValueError):
                        pass

        asyncio.run(run_bots())
    else:
        # Run only main bot if helper bot is not configured
        if WEBHOOK_ENABLED:
            logging.info(f"Starting in WEBHOOK mode on port {WEBHOOK_PORT}")
            app.run_webhook(
                listen="0.0.0.0",
                port=WEBHOOK_PORT,
                url_path="/bot_webhook",
                webhook_url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
        else:
            logging.info("Starting in POLLING mode")
            try:
                app.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )
            except Exception as e:
                logging.critical(f"run_polling exited with error: {e}", exc_info=True)
                raise

TRANSACTIONS_PER_PAGE = 5


# === re-exports of every split function/class follow ===

# from core.achievements import *  # late-bound below
# from core.dashboards import *  # late-bound below
# from core.deposits import *  # late-bound below
# from core.helpers import *  # late-bound below
# from core.levels import *  # late-bound below
# from core.max_bets import *  # late-bound below
# from core.misc import *  # late-bound below
# from core.persistence import *  # late-bound below
# from core.wallet import *  # late-bound below
# from plugins.account import *  # late-bound below
# from plugins.admin_commands import *  # late-bound below
# from plugins.ai_features import *  # late-bound below
# from plugins.bonus import *  # late-bound below
# from plugins.escrow import *  # late-bound below
# from plugins.games_blackjack import *  # late-bound below
# from plugins.games_chicken_road import *  # late-bound below
# from plugins.games_dice import *  # late-bound below
# from plugins.games_highlow import *  # late-bound below
# from plugins.games_keno import *  # late-bound below
# from plugins.games_limbo import *  # late-bound below
# from plugins.games_matches import *  # late-bound below
# from plugins.games_mines import *  # late-bound below
# from plugins.games_plinko import *  # late-bound below
# from plugins.games_roulette import *  # late-bound below
# from plugins.games_slots import *  # late-bound below
# from plugins.games_tower import *  # late-bound below
# from plugins.general import *  # late-bound below
# from plugins.jackpot import *  # late-bound below
# from plugins.leaderboard import *  # late-bound below
# from plugins.raffle import *  # late-bound below
# from plugins.referral import *  # late-bound below
# from plugins.wallet_commands import *  # late-bound below


# Auto-generated by .refactor/split_bot.py: ordered list of split modules.
_SPLIT_MODULES = ['core.achievements', 'core.dashboards', 'core.deposits', 'core.helpers', 'core.levels', 'core.max_bets', 'core.misc', 'core.persistence', 'core.wallet', 'plugins.account', 'plugins.admin_commands', 'plugins.ai_features', 'plugins.bonus', 'plugins.escrow', 'plugins.games_blackjack', 'plugins.games_chicken_road', 'plugins.games_dice', 'plugins.games_highlow', 'plugins.games_keno', 'plugins.games_limbo', 'plugins.games_matches', 'plugins.games_mines', 'plugins.games_plinko', 'plugins.games_roulette', 'plugins.games_slots', 'plugins.games_tower', 'plugins.general', 'plugins.jackpot', 'plugins.leaderboard', 'plugins.raffle', 'plugins.referral', 'plugins.wallet_commands']

def _wireup() -> None:
    """Wire all split modules together via this foundation namespace.

    The casino was originally a single 39k-line bot.py.  After
    splitting into per-feature files, each split module's
    ``from core.foundation import *`` snapshots foundation at import
    time -- so a module imported earlier cannot see names defined in
    a module imported later.

    Strategy:

    1. Import each module IN ORDER (core.* before plugins.*).  After
       each import, hoist that module's public names into foundation,
       so the NEXT module's ``from core.foundation import *`` already
       sees the previous module's symbols.  This handles class-body
       and decorator-time references like ``@check_banned``.
    2. After every module is loaded, push the FULL merged namespace
       back into every split module's __dict__ so cross-module
       function calls resolve at call time too.
    """
    import importlib, logging as _logging
    log = _logging.getLogger(__name__)
    g = globals()
    mods = []
    for mn in _SPLIT_MODULES:
        try:
            mod = importlib.import_module(mn)
        except Exception as e:
            log.warning('Failed to import split module %s: %s', mn, e, exc_info=True)
            continue
        mods.append(mod)
        # Hoist this module's public names into foundation IMMEDIATELY
        # so the next split module sees them via ``from core.foundation import *``.
        for k in dir(mod):
            if k.startswith('_'):
                continue
            g[k] = getattr(mod, k)
    # Push the fully-merged namespace back into every module so that
    # late-bound references (function bodies that resolve names at
    # call time) succeed across module boundaries.
    snapshot = {k: v for k, v in g.items() if not k.startswith('_')}
    for mod in mods:
        for k, v in snapshot.items():
            if k not in mod.__dict__:
                mod.__dict__[k] = v
    log.info('Foundation wireup complete: %d modules, %d names', len(mods), len(snapshot))

