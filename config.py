import os
from dotenv import load_dotenv

load_dotenv() # Carrega as variáveis do arquivo .env

# --- Tokens e IDs ---
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
LZT_TOKEN = os.getenv('LZT_API_TOKEN')
EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')

# --- IDs dos canais ---
TARGET_CLIENT_CHANNEL_ID = int(os.getenv('TARGET_CLIENT_CHANNEL_ID', 0))
TARGET_VENDOR_CHANNEL_ID = int(os.getenv('TARGET_VENDOR_CHANNEL_ID', 0))
TARGET_INTERNATIONAL_CHANNEL_ID = int(os.getenv('TARGET_INTERNATIONAL_CHANNEL_ID', 0))

# --- Configurações Gerais ---
API_BASE_URL = "https://api.lzt.market"
TARGET_REGION = "BR"
VALORANT_CATEGORY_ID = 13 # ID para Valorant
VALORANT_CATEGORY_NAME = "valorant"

# --- Verifica se variáveis essenciais foram carregadas ---
if not TOKEN: print("[CONFIG ERRO] DISCORD_BOT_TOKEN não encontrado no .env")
if not LZT_TOKEN: print("[CONFIG AVISO] LZT_API_TOKEN não encontrado no .env")
if not TARGET_CLIENT_CHANNEL_ID: print("[CONFIG ERRO] TARGET_CLIENT_CHANNEL_ID não encontrado ou inválido no .env")
if not TARGET_VENDOR_CHANNEL_ID: print("[CONFIG ERRO] TARGET_VENDOR_CHANNEL_ID não encontrado ou inválido no .env")
if not TARGET_INTERNATIONAL_CHANNEL_ID: print("[CONFIG ERRO] TARGET_INTERNATIONAL_CHANNEL_ID não encontrado ou inválido no .env")
if not EXCHANGE_RATE_API_KEY: print("[CONFIG AVISO] EXCHANGE_RATE_API_KEY não encontrado no .env")