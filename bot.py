import discord
from discord.ext import tasks, commands
import config
import requests
import asyncio
from datetime import datetime
import json
import io
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures
import os
import time 
import uuid  # Para gerar IDs únicos para os clientes

# --- Constantes e Configuração ---
SEEN_IDS_FILE = "seen_ids.json"
SEEN_IDS_INTERNATIONAL_FILE = "seen_ids_international.json"  # Arquivo separado para contas internacionais
ACCOUNT_MAPPING_FILE = "account_mapping.json"  # Para mapeamento entre IDs únicos e reais
ACCOUNT_MAPPING_INTERNATIONAL_FILE = "account_mapping_international.json"  # Para contas internacionais
MARGIN_CONFIG_FILE = "margin_config.json"  # Para armazenar a configuração de margem
POLLING_INTERVAL_SECONDS = 60
API_TIMEOUT = 20 
kast_zero_ids_time = 0
in_cooldown_mode = False
last_zero_ids_time_international = 0
in_cooldown_mode_international = False
COOLDOWN_DURATION = 300
MAX_SKINS_IN_GRID = 12
SKIN_GRID_COLS = 3
SKIN_THUMB_SIZE = (100, 40)
MAX_NEW_ACCOUNTS_PER_CYCLE = 3
FETCH_DETAILS_DELAY = 5
EXCHANGE_RATE_UPDATE_HOURS = 6

# Variáveis globais
seen_item_ids = set()
seen_item_ids_international = set()  # Conjunto separado para contas internacionais
usd_to_brl_rate = None
account_mapping = {}  # Mapeamento de ID único para ID real
account_mapping_international = {}  # Mapeamento para contas internacionais
price_margin = 0  # Porcentagem de margem de preço (0% por padrão)

# --- Funções de Armazenamento ---
def load_seen_ids():
    global seen_item_ids
   
    try:
        if os.path.exists(SEEN_IDS_FILE):
            with open(SEEN_IDS_FILE, 'r') as f: ids_list = json.load(f); seen_item_ids = set(ids_list)
            print(f"[INFO] Carregados {len(seen_item_ids)} IDs vistos.")
        else: seen_item_ids = set()
    except Exception as e: print(f"[ERRO] Falha ao carregar IDs: {e}"); seen_item_ids = set()

def save_seen_ids():
    try:
        with open(SEEN_IDS_FILE, 'w') as f: json.dump(list(seen_item_ids), f)
    except Exception as e: print(f"[ERRO] Falha ao salvar IDs: {e}")

def load_seen_ids_international():
    global seen_item_ids_international
   
    try:
        if os.path.exists(SEEN_IDS_INTERNATIONAL_FILE):
            with open(SEEN_IDS_INTERNATIONAL_FILE, 'r') as f: 
                ids_list = json.load(f)
                seen_item_ids_international = set(ids_list)
            print(f"[INFO] Carregados {len(seen_item_ids_international)} IDs internacionais vistos.")
        else: 
            seen_item_ids_international = set()
    except Exception as e: 
        print(f"[ERRO] Falha ao carregar IDs internacionais: {e}")
        seen_item_ids_international = set()

def save_seen_ids_international():
    try:
        with open(SEEN_IDS_INTERNATIONAL_FILE, 'w') as f: 
            json.dump(list(seen_item_ids_international), f)
    except Exception as e: 
        print(f"[ERRO] Falha ao salvar IDs internacionais: {e}")

def load_account_mapping():
    global account_mapping
    
    try:
        if os.path.exists(ACCOUNT_MAPPING_FILE):
            with open(ACCOUNT_MAPPING_FILE, 'r') as f: 
                account_mapping = json.load(f)
            print(f"[INFO] Carregados {len(account_mapping)} mapeamentos de conta.")
        else: 
            account_mapping = {}
    except Exception as e: 
        print(f"[ERRO] Falha ao carregar mapeamentos de conta: {e}")
        account_mapping = {}

def save_account_mapping():
    try:
        with open(ACCOUNT_MAPPING_FILE, 'w') as f: 
            json.dump(account_mapping, f)
    except Exception as e: 
        print(f"[ERRO] Falha ao salvar mapeamentos de conta: {e}")

def load_account_mapping_international():
    global account_mapping_international
    
    try:
        if os.path.exists(ACCOUNT_MAPPING_INTERNATIONAL_FILE):
            with open(ACCOUNT_MAPPING_INTERNATIONAL_FILE, 'r') as f: 
                account_mapping_international = json.load(f)
            print(f"[INFO] Carregados {len(account_mapping_international)} mapeamentos de conta internacional.")
        else: 
            account_mapping_international = {}
    except Exception as e: 
        print(f"[ERRO] Falha ao carregar mapeamentos de conta internacional: {e}")
        account_mapping_international = {}

def save_account_mapping_international():
    try:
        with open(ACCOUNT_MAPPING_INTERNATIONAL_FILE, 'w') as f: 
            json.dump(account_mapping_international, f)
    except Exception as e: 
        print(f"[ERRO] Falha ao salvar mapeamentos de conta internacional: {e}")

def load_price_margin():
    """Carrega a configuração de margem de preço do arquivo."""
    global price_margin
    
    try:
        if os.path.exists(MARGIN_CONFIG_FILE):
            with open(MARGIN_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                price_margin = config.get('margin', 0)
            print(f"[INFO] Margem de preço carregada: {price_margin}%")
        else:
            price_margin = 0  # Valor padrão
    except Exception as e:
        print(f"[ERRO] Falha ao carregar configuração de margem: {e}")
        price_margin = 0

def save_price_margin():
    """Salva a configuração de margem de preço no arquivo."""
    try:
        with open(MARGIN_CONFIG_FILE, 'w') as f:
            json.dump({'margin': price_margin}, f)
    except Exception as e:
        print(f"[ERRO] Falha ao salvar configuração de margem: {e}")

# --- Funções Síncronas (Executor) ---
def fetch_listings_sync(url, headers):
    """Busca a lista de contas da API LZT com mecanismo de retry."""
    
    max_retries = 3
    retry_delay = 5  # segundos
    
    for attempt in range(max_retries):
        try:
            print(f"[LZT-LIST SYNC] GET: {url} (tentativa {attempt+1}/{max_retries})")
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            print(f"[LZT-LIST SYNC] Status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code >= 500:  # Erro do servidor
                print(f"[LZT-LIST SYNC] Erro do servidor: {response.status_code}. Tentando novamente...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"[LZT-LIST SYNC] Erro não-recuperável: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"[LZT-LIST SYNC] Timeout. Tentando novamente...")
            time.sleep(retry_delay)
            continue
        except Exception as e:
            print(f"[LZT-LIST SYNC] Exceção: {e}")
            if attempt < max_retries - 1:
                print(f"[LZT-LIST SYNC] Tentando novamente em {retry_delay} segundos...")
                time.sleep(retry_delay)
            else:
                return None
    
    return None

def get_valorant_skin_details_sync(skin_uuid):
    """Busca NOME e URL do ÍCONE de uma skin na valorant-api.com."""
   
    valorant_api_url_skin = f"https://valorant-api.com/v1/weapons/skins/{skin_uuid}"
    valorant_api_url_level = f"https://valorant-api.com/v1/weapons/skinlevels/{skin_uuid}"
    skin_data = None
    try:
        response = requests.get(valorant_api_url_skin, timeout=5)
        if response.status_code == 200 and response.json().get('status') == 200: skin_data = response.json().get('data')
        elif response.status_code == 404:
            response = requests.get(valorant_api_url_level, timeout=5)
            if response.status_code == 200 and response.json().get('status') == 200: skin_data = response.json().get('data')
        if skin_data:
            name = skin_data.get('displayName', 'Desconhecido'); icon_url = skin_data.get('displayIcon')
            if name and 'standard' not in name.lower() and icon_url: return {'name': name, 'icon_url': icon_url, 'uuid': skin_uuid}
        return None
    except Exception as e: print(f"[VAL-API SYNC] Erro skin {skin_uuid}: {e}"); return None

def download_image_sync(url):
    """Baixa uma imagem de uma URL e retorna os bytes."""
   
    try:
        response = requests.get(url, stream=True, timeout=10); response.raise_for_status()
        return response.content
    except Exception as e: print(f"[DOWNLOAD SYNC] Erro {url}: {e}"); return None

def create_skin_grid_sync(skin_details_list, grid_cols=4, card_width=150, card_height=90, padding=5):
    """Cria uma grade de cartões de skins com imagem e nome, exatamente no estilo do exemplo."""
    
    if not skin_details_list:
        return None
    
    cards = []
    # Fonte para o nome das skins
    try:
        # Tente carregar uma fonte, com fallback para a padrão
        font = ImageFont.truetype("arial.ttf", 10)  # Fonte menor para caber nomes longos
    except IOError:
        font = ImageFont.load_default()
    
    for skin in skin_details_list:
        try:
            name = skin.get('name', 'Desconhecido')
            img_bytes = skin.get('icon_bytes')
            if not img_bytes:
                continue
                
            # Crie o cartão base (fundo escuro igual ao da imagem)
            card = Image.new('RGBA', (card_width, card_height), (24, 25, 28, 255))
            
            # Abra a imagem da skin
            img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            
            # Ajuste o tamanho da imagem com proporções fixas
            img_height = 60  # Altura fixa para a imagem
            ratio = img_height / img.height
            img_width = int(img.width * ratio)
            
            # Se a largura for maior que o cartão, redimensione novamente
            if img_width > (card_width - 10):
                img_width = card_width - 10
                ratio = img_width / img.width
                img_height = int(img.height * ratio)
            
            img = img.resize((img_width, img_height), Image.Resampling.LANCZOS)
            
            # Posicione a imagem centralizada no cartão
            x_offset = (card_width - img_width) // 2
            y_offset = 5  # Margem superior pequena
            
            card.paste(img, (x_offset, y_offset), img)
            
            # Adicione o nome da skin na parte inferior
            draw = ImageDraw.Draw(card)
            
            # Truncar texto se for muito longo
            if len(name) > 20:
                name = name[:18] + "..."
                
            text_width = draw.textlength(name, font=font)
            text_x = (card_width - text_width) // 2
            text_y = card_height - 18  # Posicionar o texto na parte inferior
            
            # Desenhar o texto com sombra para legibilidade
            draw.text((text_x+1, text_y+1), name, font=font, fill=(0, 0, 0, 180))  # sombra
            draw.text((text_x, text_y), name, font=font, fill=(255, 255, 255, 255))  # texto
            
            cards.append(card)
        except Exception as e:
            print(f"[PILLOW SYNC] Erro ao criar cartão para {name}: {e}")
            continue
    
    if not cards:
        return None
    
    # Calcule o tamanho da grade
    num_cards = len(cards)
    grid_cols = min(grid_cols, num_cards)
    grid_rows = (num_cards + grid_cols - 1) // grid_cols
    
    # Crie a imagem da grade
    grid_width = (card_width * grid_cols) + (padding * (grid_cols + 1))
    grid_height = (card_height * grid_rows) + (padding * (grid_rows + 1))
    grid_image = Image.new('RGBA', (grid_width, grid_height), (18, 18, 20, 255))  # Fundo bem escuro
    
    # Coloque os cartões na grade
    current_x, current_y = padding, padding
    for i, card in enumerate(cards):
        grid_image.paste(card, (current_x, current_y), card)
        current_x += card_width + padding
        if (i + 1) % grid_cols == 0:
            current_y += card_height + padding
            current_x = padding
    
    # Salve e retorne os bytes da imagem final
    final_image_bytes = io.BytesIO()
    grid_image.save(final_image_bytes, format='PNG')
    final_image_bytes.seek(0)
    
    print(f"[PILLOW SYNC] Grade {grid_cols}x{grid_rows} de cartões criada.")
    return final_image_bytes

def fetch_and_create_skin_grid_sync(skin_uuids):
    """Busca detalhes, baixa ícones e cria a imagem da grade."""
    
    print(f"[SKIN SYNC] Buscando detalhes para {min(len(skin_uuids), MAX_SKINS_IN_GRID)} UUIDs...")
    skin_details_list = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_uuid = {executor.submit(get_valorant_skin_details_sync, uuid): uuid for uuid in skin_uuids[:MAX_SKINS_IN_GRID]}
        for future in concurrent.futures.as_completed(future_to_uuid):
            details = future.result()
            if details:
                skin_details_list.append(details)

    if not skin_details_list:
        return None
        
    # Adicione os bytes das imagens aos detalhes das skins
    processed_skins = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for skin in skin_details_list:
            if 'icon_url' in skin:
                future = executor.submit(download_image_sync, skin['icon_url'])
                icon_bytes = future.result()
                if icon_bytes:
                    # Crie uma nova entrada com nome e bytes da imagem
                    processed_skins.append({
                        'name': skin['name'],
                        'icon_bytes': icon_bytes
                    })
                else:
                    print(f"[SKIN SYNC] Falha ao baixar ícone para {skin['name']}")
    
    if not processed_skins:
        return None
        
    print(f"[SKIN SYNC] Criando imagem da grade com {len(processed_skins)} skins...")
    grid_image_bytes = create_skin_grid_sync(processed_skins, grid_cols=SKIN_GRID_COLS)
    return grid_image_bytes

def fetch_item_details_sync(item_id, headers):
    """Busca os detalhes de um item específico da API LZT com mecanismo de retry."""
    
    api_endpoint = f"{config.API_BASE_URL}/{item_id}"
    max_retries = 3
    retry_delay = 5  # segundos
    
    for attempt in range(max_retries):
        try:
            print(f"[LZT-DETAIL SYNC] GET: {api_endpoint} (tentativa {attempt+1}/{max_retries})")
            response = requests.get(api_endpoint, headers=headers, timeout=API_TIMEOUT)
            print(f"[LZT-DETAIL SYNC] Status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code >= 500:  # Erro do servidor
                print(f"[LZT-DETAIL SYNC] Erro do servidor: {response.status_code}. Tentando novamente...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"[LZT-DETAIL SYNC] Erro não-recuperável: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"[LZT-DETAIL SYNC] Timeout. Tentando novamente...")
            time.sleep(retry_delay)
            continue
        except Exception as e:
            print(f"[LZT-DETAIL SYNC] Exceção: {e}")
            if attempt < max_retries - 1:
                print(f"[LZT-DETAIL SYNC] Tentando novamente em {retry_delay} segundos...")
                time.sleep(retry_delay)
            else:
                return None
    
    return None

def fetch_exchange_rate_sync():
    """Busca a taxa de câmbio USD para BRL."""
    if not config.EXCHANGE_RATE_API_KEY:
        print("[RATE SYNC] Chave da API de Câmbio não configurada.")
        return None
    api_url = f"https://v6.exchangerate-api.com/v6/{config.EXCHANGE_RATE_API_KEY}/latest/USD"
    try:
        print(f"[RATE SYNC] Buscando taxa de câmbio de {api_url}")
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("result") == "success":
            rate = data.get("conversion_rates", {}).get("BRL")
            print(f"[RATE SYNC] Taxa USD->BRL obtida: {rate}")
            return rate
        else:
            print(f"[RATE SYNC] Erro na resposta da API de Câmbio: {data.get('error-type')}")
            return None
    except Exception as e:
        print(f"[RATE SYNC] Exceção ao buscar taxa de câmbio: {e}")
        return None

# --- Fim das Funções Síncronas ---

# --- Configuração do Bot ---
intents = discord.Intents.default()
intents.message_content = True  # Necessário para comandos

# Cria o cliente do bot com suporte a comandos
bot = commands.Bot(command_prefix='/', intents=intents)

async def generate_unique_id():
    """Gera um ID único curto para identificação da conta pelo cliente."""
    # Gera um UUID e pega apenas os primeiros 6 caracteres
    return str(uuid.uuid4())[:6].upper()

async def process_new_account(item_id, item_data):
    """Processa uma nova conta, gerando ID único e enviando apenas para o canal do cliente."""
    # Gerar um ID único para a conta
    unique_id = await generate_unique_id()
    
    # Salvar o mapeamento para uso futuro
    account_mapping[unique_id] = item_id
    save_account_mapping()
    
    # Enviar apenas para o canal do cliente (informações limitadas com margem de preço)
    await send_client_embed(config.TARGET_CLIENT_CHANNEL_ID, item_id, item_data, unique_id)
    
    print(f"[INFO] Conta {item_id} processada com ID de cliente {unique_id}")
    return unique_id

async def process_new_international_account(item_id, item_data):
    """Processa uma nova conta internacional, gerando ID único e enviando apenas para o canal internacional."""
    # Gerar um ID único para a conta
    unique_id = await generate_unique_id()
    
    # Salvar o mapeamento para uso futuro
    account_mapping_international[unique_id] = item_id
    save_account_mapping_international()
    
    # Enviar para o canal internacional
    await send_client_embed(config.TARGET_INTERNATIONAL_CHANNEL_ID, item_id, item_data, unique_id, is_international=True)
    
    print(f"[INFO] Conta internacional {item_id} processada com ID de cliente {unique_id}")
    return unique_id

async def send_vendor_embed(target_channel_id, item_id, item_data, unique_id):
    """Formata e envia o embed com todas as informações para o canal do vendedor."""
    channel = bot.get_channel(target_channel_id)
    if not channel:
        print(f"[ERRO] Canal do vendedor com ID {target_channel_id} não encontrado.")
        try:
            channel = await bot.fetch_channel(target_channel_id)
        except Exception as e:
            print(f"[ERRO] Não foi possível buscar o canal do vendedor: {e}")
            return
            
        if not channel:
            print(f"[ERRO CRÍTICO] Impossível encontrar o canal do vendedor {target_channel_id}.")
            return

    account_url = f"https://lzt.market/{item_id}"

    # --- Extração de Dados Principais ---
    region = item_data.get('riot_valorant_region', 'N/A')
    title = item_data.get('title', 'Título N/A')
    price_original = item_data.get('price', 0)
    currency_original = item_data.get('price_currency', '').upper()
    skin_count_total = item_data.get('riot_valorant_skin_count', 'N/A')
    skin_count_guns = 0
    skin_count_knifes = 0
    
    # Contar skins de armas e facas separadamente
    if 'valorantInventory' in item_data and 'WeaponSkins' in item_data['valorantInventory']:
        skin_count_guns = len(item_data['valorantInventory']['WeaponSkins'])
    
    if 'valorantInventory' in item_data and 'KnifesSkins' in item_data['valorantInventory']:
        skin_count_knifes = len(item_data['valorantInventory']['KnifesSkins'])
    
    vp_amount = item_data.get('riot_valorant_wallet_vp', 'N/A')
    rp_amount = item_data.get('riot_valorant_wallet_rp', 'N/A')
    inventory_vp_value = item_data.get('riot_valorant_inventory_value', 'N/A')
    current_rank = item_data.get('valorantRankTitle', 'N/A')
    last_rank = item_data.get('valorantLastRankTitle', 'N/A')
    level = item_data.get('riot_valorant_level', 'N/A')
    
    # Preparar descrição com skins especiais
    description = f"**{title}**"
    
    # Conversão de Preço para BRL (sem margem para o vendedor)
    price_display = f"{price_original} {currency_original}"
    if currency_original == 'USD' and usd_to_brl_rate:
        try:
            price_in_brl = float(price_original) * usd_to_brl_rate
            price_display = f"R$ {price_in_brl:.2f}"
        except Exception as e:
            print(f"[ERRO] Erro ao converter preço: {e}")
    
    # Formatação da data
    timestamp = item_data.get('account_last_activity', None)
    last_activity_str = "N/A"
    if timestamp:
        try:
            last_activity_str = datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            last_activity_str = "Data inválida"

    # --- Montar Embed para Vendedor (informação completa) ---
    embed = discord.Embed(
        title=f"✨ Detalhes da Conta {region} ✨",
        description=description,
        color=0x2F3136
    )
    
    # Primeira linha de campos
    embed.add_field(name="💰 Inventário (VP)", value=f"{inventory_vp_value}", inline=True)
    embed.add_field(name="🔫 Skins", value=f"{skin_count_total}", inline=True)
    embed.add_field(name="💸 VP Carteira", value=f"{vp_amount}", inline=True)
    
    # Segunda linha de campos
    embed.add_field(name="💎 RP Carteira", value=f"{rp_amount}", inline=True)
    embed.add_field(name="🌍 Região", value=f"{region}", inline=True)
    embed.add_field(name="💲 Preço Original", value=f"{price_display}", inline=True)
    
    # Terceira linha de campos
    embed.add_field(name="🏆 Rank Atual", value=f"{current_rank}", inline=True)
    embed.add_field(name="🏅 Último Rank", value=f"{last_rank}", inline=True)
    embed.add_field(name="📊 Level", value=f"{level}", inline=True)
    
    # Última atividade
    embed.add_field(name="📅 Última Atividade", value=last_activity_str, inline=False)
    
    # Link para o LZT Market
    embed.add_field(name="🔗 Link para Compra", value=account_url, inline=False)
    
    # Adicionar o ID único para referência
    embed.add_field(name="🔑 ID Cliente", value=unique_id, inline=False)
    
    # Mostrar informação sobre margem (se aplicável)
    if price_margin > 0:
        # Calcular o preço com margem para mostrar a diferença
        price_with_margin = price_display
        if currency_original == 'USD' and usd_to_brl_rate:
            try:
                price_in_brl = float(price_original) * usd_to_brl_rate
                price_with_margin_value = price_in_brl * (1 + (price_margin / 100))
                price_with_margin = f"R$ {price_with_margin_value:.2f}"
            except Exception as e:
                print(f"[ERRO] Erro ao calcular preço com margem: {e}")
        elif price_original:
            try:
                price_with_margin_value = float(price_original) * (1 + (price_margin / 100))
                price_with_margin = f"{price_with_margin_value:.2f} {currency_original}"
            except Exception as e:
                print(f"[ERRO] Erro ao calcular preço com margem: {e}")
        
        embed.add_field(name="📈 Informação de Margem", 
                       value=f"Margem atual: **{price_margin}%**\nPreço mostrado ao cliente: **{price_with_margin}**", 
                       inline=False)
    
    # Footer
    embed.set_footer(text=f"ID Real: {item_id} | Verificado por {bot.user.name}")

    # --- Geração e Envio da Grade de Skins ---
    grid_image_file = None
    skins_list_ids = []
    
    # Combinar skins de armas e facas
    if 'valorantInventory' in item_data:
        if 'WeaponSkins' in item_data['valorantInventory']:
            skins_list_ids.extend(item_data['valorantInventory']['WeaponSkins'])
        if 'KnifesSkins' in item_data['valorantInventory']:
            skins_list_ids.extend(item_data['valorantInventory']['KnifesSkins'])
    
    if skins_list_ids:
        print(f"[ASYNC] Gerando grade de {len(skins_list_ids)} skins para item {item_id}...")
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            grid_bytes = await loop.run_in_executor(
                pool, fetch_and_create_skin_grid_sync, skins_list_ids
            )

        if grid_bytes:
            grid_image_file = discord.File(fp=grid_bytes, filename="skin_grid.png")
            embed.set_image(url="attachment://skin_grid.png")
        else:
            embed.add_field(name="🖼️ Skins Preview", value="Falha ao gerar preview.", inline=False)
    else:
        embed.add_field(name="🖼️ Skins Preview", value="Nenhuma skin listada para gerar preview.", inline=False)

    # --- Enviar a Mensagem Final ---
    try:
        await channel.send(embed=embed, file=grid_image_file if grid_image_file else None)
        print(f"[DISCORD] Embed do vendedor enviado para item {item_id} no canal {target_channel_id}")
    except Exception as e:
        print(f"[ERRO DISCORD] Erro ao enviar mensagem do vendedor para item {item_id}: {e}")


async def send_client_embed(target_channel_id, item_id, item_data, unique_id, is_international=False):
    """Formata e envia o embed com informações limitadas para o canal do cliente."""
    channel = bot.get_channel(target_channel_id)
    if not channel:
        print(f"[ERRO] Canal do cliente com ID {target_channel_id} não encontrado.")
        try:
            channel = await bot.fetch_channel(target_channel_id)
        except Exception as e:
            print(f"[ERRO] Não foi possível buscar o canal do cliente: {e}")
            return
            
        if not channel:
            print(f"[ERRO CRÍTICO] Impossível encontrar o canal do cliente {target_channel_id}.")
            return

    # --- Extração de Dados Principais ---
    region = item_data.get('riot_valorant_region', 'N/A')
    price_original = item_data.get('price', 0)
    currency_original = item_data.get('price_currency', '').upper()
    skin_count_total = item_data.get('riot_valorant_skin_count', 'N/A')
    vp_amount = item_data.get('riot_valorant_wallet_vp', 'N/A')
    rp_amount = item_data.get('riot_valorant_wallet_rp', 'N/A')
    inventory_vp_value = item_data.get('riot_valorant_inventory_value', 'N/A')
    current_rank = item_data.get('valorantRankTitle', 'N/A')
    last_rank = item_data.get('valorantLastRankTitle', 'N/A')
    level = item_data.get('riot_valorant_level', 'N/A')
    
    # Conversão de Preço para BRL com aplicação da margem
    price_display = f"{price_original} {currency_original}"
    if currency_original == 'USD' and usd_to_brl_rate:
        try:
            # Aplica a conversão de moeda
            price_in_brl = float(price_original) * usd_to_brl_rate
            
            # Aplica a margem de preço
            if price_margin > 0:
                price_with_margin = price_in_brl * (1 + (price_margin / 100))
                price_display = f"R$ {price_with_margin:.2f}"
            else:
                price_display = f"R$ {price_in_brl:.2f}"
        except Exception as e:
            print(f"[ERRO] Erro ao converter/aplicar margem ao preço: {e}")
    elif price_margin > 0:
        # Se não for USD ou não tiver taxa de câmbio, mas tiver margem
        try:
            price_with_margin = float(price_original) * (1 + (price_margin / 100))
            price_display = f"{price_with_margin:.2f} {currency_original}"
        except Exception as e:
            print(f"[ERRO] Erro ao aplicar margem ao preço: {e}")
    
    # --- Montar Embed para Cliente (informação limitada) ---
    title_text = "✨ Nova Conta BR Disponível ✨"
    description_text = "**Conta Valorant**"
    
    # Customizar para contas internacionais
    if is_international:
        title_text = f"✨ Nova Conta {region} Disponível ✨"
        description_text = "**Conta Valorant Internacional**"
    
    embed = discord.Embed(
        title=title_text,
        description=description_text,
        color=0x2F3136
    )
    
    # Primeira linha de campos
    embed.add_field(name="💰 Inventário (VP)", value=f"{inventory_vp_value}", inline=True)
    embed.add_field(name="🔫 Skins", value=f"{skin_count_total}", inline=True)
    embed.add_field(name="💸 VP Carteira", value=f"{vp_amount}", inline=True)
    
    # Segunda linha de campos
    embed.add_field(name="💎 RP Carteira", value=f"{rp_amount}", inline=True)
    embed.add_field(name="🌍 Região", value=f"{region}", inline=True)
    embed.add_field(name="💲 Preço", value=f"{price_display}", inline=True)
    
    # Terceira linha de campos
    embed.add_field(name="🏆 Rank Atual", value=f"{current_rank}", inline=True)
    embed.add_field(name="🏅 Último Rank", value=f"{last_rank}", inline=True)
    embed.add_field(name="📊 Level", value=f"{level}", inline=True)
    
    # Formatação da data para o cliente
    timestamp = item_data.get('account_last_activity', None)
    last_activity_str = "N/A"
    if timestamp:
        try:
            last_activity_str = datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            last_activity_str = "Data inválida"
            
    # Adicionar campo de última atividade
    embed.add_field(name="📅 Última Atividade", value=last_activity_str, inline=False)
    
    # ID da conta para o cliente
    embed.add_field(name="🔑 ID da Conta", value=unique_id, inline=False)
    embed.add_field(name="📢 Como Comprar", value="Entre em contato com um vendedor e informe o ID da conta para adquirir.", inline=False)
    
    # Footer (sem o ID real)
    embed.set_footer(text=f"Verificado por {bot.user.name}")

    # --- Geração e Envio da Grade de Skins ---
    grid_image_file = None
    skins_list_ids = []
    
    # Combinar skins de armas e facas
    if 'valorantInventory' in item_data:
        if 'WeaponSkins' in item_data['valorantInventory']:
            skins_list_ids.extend(item_data['valorantInventory']['WeaponSkins'])
        if 'KnifesSkins' in item_data['valorantInventory']:
            skins_list_ids.extend(item_data['valorantInventory']['KnifesSkins'])
    
    if skins_list_ids:
        print(f"[ASYNC] Gerando grade de {len(skins_list_ids)} skins para item {item_id} (cliente)...")
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            grid_bytes = await loop.run_in_executor(
                pool, fetch_and_create_skin_grid_sync, skins_list_ids
            )

        if grid_bytes:
            grid_image_file = discord.File(fp=grid_bytes, filename="skin_grid.png")
            embed.set_image(url="attachment://skin_grid.png")
        else:
            embed.add_field(name="🖼️ Skins Preview", value="Falha ao gerar preview.", inline=False)
    else:
        embed.add_field(name="🖼️ Skins Preview", value="Nenhuma skin listada para gerar preview.", inline=False)

    # --- Enviar a Mensagem Final ---
    try:
        await channel.send(embed=embed, file=grid_image_file if grid_image_file else None)
        print(f"[DISCORD] Embed do cliente enviado para item {item_id} no canal {target_channel_id}")
    except Exception as e:
        print(f"[ERRO DISCORD] Erro ao enviar mensagem do cliente para item {item_id}: {e}")


# --- Comando de Busca por ID ---
@bot.command(name="buscar")
async def search_account(ctx, account_id: str):
    """Comando para buscar uma conta pelo ID fornecido pelo cliente."""
    # Verificar se o comando foi enviado no canal do vendedor
    if ctx.channel.id != config.TARGET_VENDOR_CHANNEL_ID:
        await ctx.send("Este comando só pode ser usado no canal do vendedor.")
        return
    
    # Carregar mapeamento de contas, se ainda não estiver carregado
    if not account_mapping:
        load_account_mapping()
    
    if not account_mapping_international:
        load_account_mapping_international()
    
    # Verificar se o ID existe no mapeamento BR
    if account_id in account_mapping:
        real_item_id = account_mapping[account_id]
        
        # Buscar detalhes da conta
        headers = {'Authorization': f'Bearer {config.LZT_TOKEN}'}
        loop = asyncio.get_running_loop()
        
        with concurrent.futures.ThreadPoolExecutor() as pool:
            item_details_data = await loop.run_in_executor(
                pool, fetch_item_details_sync, real_item_id, headers
            )
        
        if item_details_data and 'item' in item_details_data:
            await ctx.send(f"✅ Conta BR encontrada! ID do cliente: {account_id}")
            await send_vendor_embed(ctx.channel.id, real_item_id, item_details_data['item'], account_id)
        else:
            await ctx.send(f"⚠️ Conta com ID {account_id} encontrada no mapeamento BR, mas falha ao buscar detalhes atualizados. ID real: {real_item_id}")
        return
    
    # Verificar se o ID existe no mapeamento internacional
    if account_id in account_mapping_international:
        real_item_id = account_mapping_international[account_id]
        
        # Buscar detalhes da conta
        headers = {'Authorization': f'Bearer {config.LZT_TOKEN}'}
        loop = asyncio.get_running_loop()
        
        with concurrent.futures.ThreadPoolExecutor() as pool:
            item_details_data = await loop.run_in_executor(
                pool, fetch_item_details_sync, real_item_id, headers
            )
        
        if item_details_data and 'item' in item_details_data:
            region = item_details_data['item'].get('riot_valorant_region', 'N/A')
            await ctx.send(f"✅ Conta Internacional ({region}) encontrada! ID do cliente: {account_id}")
            await send_vendor_embed(ctx.channel.id, real_item_id, item_details_data['item'], account_id)
        else:
            await ctx.send(f"⚠️ Conta com ID {account_id} encontrada no mapeamento internacional, mas falha ao buscar detalhes atualizados. ID real: {real_item_id}")
        return
    
    # Se chegou aqui, não encontrou em nenhum mapeamento
    await ctx.send(f"❌ Nenhuma conta encontrada com o ID {account_id}.")

# --- Comando para definir a margem de preço ---
@bot.command(name="margem")
async def set_price_margin(ctx, percentage: float):
    """Define a margem de preço a ser adicionada para os clientes (em porcentagem)."""
    global price_margin
    
    # Verificar se o comando foi enviado no canal do vendedor
    if ctx.channel.id != config.TARGET_VENDOR_CHANNEL_ID:
        await ctx.send("Este comando só pode ser usado no canal do vendedor.")
        return
    
    # Verificar se o valor é válido
    if percentage < 0:
        await ctx.send("❌ A margem não pode ser negativa.")
        return
    
    # Atualizar a margem
    price_margin = percentage
    save_price_margin()
    
    await ctx.send(f"✅ Margem de preço definida para **{percentage}%**.\nOs preços mostrados aos clientes agora terão um aumento de {percentage}%.")

# --- Comando para ver a margem atual ---
@bot.command(name="vermargem")
async def view_price_margin(ctx):
    """Exibe a margem de preço atual."""
    # Verificar se o comando foi enviado no canal do vendedor
    if ctx.channel.id != config.TARGET_VENDOR_CHANNEL_ID:
        await ctx.send("Este comando só pode ser usado no canal do vendedor.")
        return
    
    await ctx.send(f"📊 A margem de preço atual é de **{price_margin}%**.")

# --- Loop de Tarefas para Verificar Novas Contas BR ---
@tasks.loop(seconds=POLLING_INTERVAL_SECONDS)
async def check_new_accounts():
    global seen_item_ids, kast_zero_ids_time, in_cooldown_mode
    current_time = time.time()
    
    # Verifica se estamos em período de cooldown
    if in_cooldown_mode:
        elapsed = current_time - kast_zero_ids_time
        if elapsed < COOLDOWN_DURATION:
            remaining = COOLDOWN_DURATION - elapsed
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Em cooldown BR por mais {remaining:.0f} segundos...")
            return
        else:
            # Saímos do período de cooldown
            in_cooldown_mode = False
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Saindo do período de cooldown BR!")
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando verificação de novas contas BR...")
    if not config.LZT_TOKEN or not config.TARGET_CLIENT_CHANNEL_ID:
        print("[TASK ERRO] Token LZT ou Canal do Cliente não configurado.")
        return

    list_url = f"{config.API_BASE_URL}/riot/?pmax=50&daybreak=7&nsb=1&knife=1&valorant_region[]={config.TARGET_REGION}&order_by=published_date&order_direction=desc"
    headers = {'Authorization': f'Bearer {config.LZT_TOKEN}'}
    loop = asyncio.get_running_loop()

    listing_data = None
    with concurrent.futures.ThreadPoolExecutor() as pool:
        listing_data = await loop.run_in_executor(pool, fetch_listings_sync, list_url, headers)

    if listing_data is None or 'items' not in listing_data:
        print("[TASK ERRO] Falha ao buscar/parsear lista de contas LZT.")
        return

    current_items = listing_data.get('items', [])
    if not current_items: 
        print("[TASK INFO] Nenhuma conta na listagem atual.")
        return

    current_item_ids = {item.get('item_id') for item in current_items if item.get('item_id')}
    print(f"[TASK INFO] IDs atuais BR: {len(current_item_ids)}")
    new_ids = sorted(list(current_item_ids - seen_item_ids), reverse=True)
    print(f"[TASK INFO] IDs novos BR: {len(new_ids)}")

    if not new_ids:
        # Não há novos IDs, ativar o cooldown
        print(f"[TASK INFO] Nenhum ID novo BR encontrado. Entrando em modo de cooldown por {COOLDOWN_DURATION} segundos...")
        kast_zero_ids_time = current_time
        in_cooldown_mode = True
        
        # Atualizar IDs vistos para evitar verificações desnecessárias depois do cooldown
        if current_item_ids != seen_item_ids:
            print("[TASK INFO] Atualizando vistos com IDs atuais BR.")
            seen_item_ids = current_item_ids
            save_seen_ids()
        return
    
    # Processar novos IDs
    print(f"[TASK INFO] Processando {min(len(new_ids), MAX_NEW_ACCOUNTS_PER_CYCLE)} novos IDs BR: {new_ids[:MAX_NEW_ACCOUNTS_PER_CYCLE]}")
    newly_processed_ids = set()
    processed_count = 0
    for item_id in new_ids:
        if item_id is None: continue
        if processed_count >= MAX_NEW_ACCOUNTS_PER_CYCLE:
             print(f"[TASK INFO] Limite de {MAX_NEW_ACCOUNTS_PER_CYCLE} contas BR por ciclo atingido.")
             break # Sai do loop se atingir o limite

        item_details_data = None
        with concurrent.futures.ThreadPoolExecutor() as pool:
             item_details_data = await loop.run_in_executor(pool, fetch_item_details_sync, item_id, headers)

        if item_details_data and 'item' in item_details_data:
            # Processar a conta (enviar apenas para o canal do cliente)
            await process_new_account(item_id, item_details_data['item'])
            newly_processed_ids.add(item_id)
            processed_count += 1
            await asyncio.sleep(FETCH_DETAILS_DELAY) # Delay entre processar cada conta nova
        else:
            print(f"[TASK ERRO] Falha ao obter detalhes para ID BR: {item_id}")
            newly_processed_ids.add(item_id) # Adiciona mesmo se falhar para não tentar de novo

    seen_item_ids.update(newly_processed_ids)
    save_seen_ids()

# --- Loop de Tarefas para Verificar Novas Contas Internacionais ---
@tasks.loop(seconds=POLLING_INTERVAL_SECONDS)
async def check_new_international_accounts():
    global seen_item_ids_international, last_zero_ids_time_international, in_cooldown_mode_international
    current_time = time.time()
    
    # Verifica se estamos em período de cooldown
    if in_cooldown_mode_international:
        elapsed = current_time - last_zero_ids_time_international
        if elapsed < COOLDOWN_DURATION:
            remaining = COOLDOWN_DURATION - elapsed
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Em cooldown Internacional por mais {remaining:.0f} segundos...")
            return
        else:
            # Saímos do período de cooldown
            in_cooldown_mode_international = False
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Saindo do período de cooldown Internacional!")
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando verificação de novas contas internacionais...")
    if not config.LZT_TOKEN or not config.TARGET_INTERNATIONAL_CHANNEL_ID:
        print("[TASK ERRO] Token LZT ou Canal Internacional não configurado.")
        return

    # URL para contas internacionais com filtros específicos:
    # - Preço máximo equivalente a 230 BRL
    # - VP mínimo de 15.000
    # - Regiões EU, AP, NA e LA (excluindo BR e KR)
    max_price_usd = 30  # Valor aproximado, será convertido
    if usd_to_brl_rate:
        try:
            max_price_usd = 230 / usd_to_brl_rate
            print(f"[TASK INFO] Preço máximo: R$ 230,00 → ${max_price_usd:.2f}")
        except Exception as e:
            print(f"[TASK ERRO] Erro ao calcular preço máximo em USD: {e}")
    
    # Montando a URL com todos os filtros
    list_url = f"{config.API_BASE_URL}/riot/?pmax={max_price_usd:.2f}&inv_min=15000&valorant_region[]=EU&valorant_region[]=AP&valorant_region[]=NA&valorant_region[]=LA&daybreak=7&nsb=1&knife=1&order_by=published_date&order_direction=desc"
    
    headers = {'Authorization': f'Bearer {config.LZT_TOKEN}'}
    loop = asyncio.get_running_loop()

    listing_data = None
    with concurrent.futures.ThreadPoolExecutor() as pool:
        listing_data = await loop.run_in_executor(pool, fetch_listings_sync, list_url, headers)

    if listing_data is None or 'items' not in listing_data:
        print("[TASK ERRO] Falha ao buscar/parsear lista de contas LZT para Internacional.")
        return

    current_items = listing_data.get('items', [])
    if not current_items: 
        print("[TASK INFO] Nenhuma conta internacional na listagem atual.")
        return

    current_item_ids = {item.get('item_id') for item in current_items if item.get('item_id')}
    print(f"[TASK INFO] IDs atuais Internacional: {len(current_item_ids)}")
    new_ids = sorted(list(current_item_ids - seen_item_ids_international), reverse=True)
    print(f"[TASK INFO] IDs novos Internacional: {len(new_ids)}")

    if not new_ids:
        # Não há novos IDs, ativar o cooldown
        print(f"[TASK INFO] Nenhum ID novo Internacional encontrado. Entrando em modo de cooldown por {COOLDOWN_DURATION} segundos...")
        last_zero_ids_time_international = current_time
        in_cooldown_mode_international = True
        
        # Atualizar IDs vistos para evitar verificações desnecessárias depois do cooldown
        if current_item_ids != seen_item_ids_international:
            print("[TASK INFO] Atualizando vistos com IDs atuais Internacional.")
            seen_item_ids_international = current_item_ids
            save_seen_ids_international()
        return
    
    # Processar novos IDs
    print(f"[TASK INFO] Processando {min(len(new_ids), MAX_NEW_ACCOUNTS_PER_CYCLE)} novos IDs Internacional: {new_ids[:MAX_NEW_ACCOUNTS_PER_CYCLE]}")
    newly_processed_ids = set()
    processed_count = 0
    
    for item_id in new_ids:
        if item_id is None: continue
        if processed_count >= MAX_NEW_ACCOUNTS_PER_CYCLE:
             print(f"[TASK INFO] Limite de {MAX_NEW_ACCOUNTS_PER_CYCLE} contas Internacional por ciclo atingido.")
             break # Sai do loop se atingir o limite

        item_details_data = None
        with concurrent.futures.ThreadPoolExecutor() as pool:
             item_details_data = await loop.run_in_executor(pool, fetch_item_details_sync, item_id, headers)

        if item_details_data and 'item' in item_details_data:
            # Como os filtros já foram aplicados na API, podemos processar diretamente
            await process_new_international_account(item_id, item_details_data['item'])
            newly_processed_ids.add(item_id)
            processed_count += 1
            await asyncio.sleep(FETCH_DETAILS_DELAY) # Delay entre processar cada conta nova
        else:
            print(f"[TASK ERRO] Falha ao obter detalhes para ID Internacional: {item_id}")
            newly_processed_ids.add(item_id) # Adiciona mesmo se falhar para não tentar de novo

    seen_item_ids_international.update(newly_processed_ids)
    save_seen_ids_international()

# --- Loop de Tarefas para Atualizar Taxa de Câmbio ---
@tasks.loop(hours=EXCHANGE_RATE_UPDATE_HOURS)
async def update_exchange_rate():
    global usd_to_brl_rate
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Atualizando taxa de câmbio USD -> BRL...")
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        rate = await loop.run_in_executor(pool, fetch_exchange_rate_sync)

    if rate is not None:
        usd_to_brl_rate = rate
        print(f"[INFO] Taxa de câmbio atualizada: 1 USD = {usd_to_brl_rate} BRL")
    else:
        print("[ERRO] Não foi possível atualizar a taxa de câmbio.")

# --- Eventos do Bot e Inicialização ---

@bot.event
async def on_connect(): print("Bot conectado ao Discord.")
@bot.event
async def on_disconnect(): print("Bot desconectado do Discord.")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    
    # Listar todos os servidores e canais visíveis
    print('Servidores e canais visíveis:')
    for guild in bot.guilds:
        print(f'- Servidor: {guild.name} (ID: {guild.id})')
        for channel in guild.text_channels:
            try:
                # Tenta acessar o canal para verificar permissões
                await channel.guild.fetch_channel(channel.id)
                print(f'  - Canal: {channel.name} (ID: {channel.id}) - Acessível')
            except Exception as e:
                print(f'  - Canal: {channel.name} (ID: {channel.id}) - Não acessível: {e}')
    
    print('------')
    # Carrega IDs vistos, mapeamento de contas e configuração de margem
    load_seen_ids()
    load_seen_ids_international()
    load_account_mapping()
    load_account_mapping_international()
    load_price_margin()
    
    if not update_exchange_rate.is_running():
        update_exchange_rate.start() # Inicia loop da taxa de câmbio
    if not check_new_accounts.is_running():
        check_new_accounts.start()
    if not check_new_international_accounts.is_running():
        check_new_international_accounts.start()

# --- Bloco final para rodar o Bot ---
if __name__ == "__main__":
    # Verificações de token e canal alvo
    if not config.TOKEN: print("ERRO CRÍTICO: Token Discord não encontrado!"); exit()
    if not config.LZT_TOKEN: print("[AVISO] Token API LZT não encontrado.")
    if not config.TARGET_CLIENT_CHANNEL_ID: print("[ERRO CRÍTICO] TARGET_CLIENT_CHANNEL_ID não definido!"); exit()
    if not config.TARGET_VENDOR_CHANNEL_ID: print("[ERRO CRÍTICO] TARGET_VENDOR_CHANNEL_ID não definido!"); exit()
    if not config.TARGET_INTERNATIONAL_CHANNEL_ID: print("[ERRO CRÍTICO] TARGET_INTERNATIONAL_CHANNEL_ID não definido!"); exit()
    if not config.EXCHANGE_RATE_API_KEY: print("[AVISO] Chave da API de Câmbio não definida, a conversão para BRL não funcionará.")

    try: bot.run(config.TOKEN)
    except discord.errors.LoginFailure: print("ERRO CRÍTICO: Falha no login do Discord - Token inválido.")
    except discord.errors.PrivilegedIntentsRequired: print("ERRO CRÍTICO: Intents Privilegiadas não habilitadas!")
    except Exception as e: print(f"ERRO CRÍTICO ao iniciar: {e}"); import traceback; traceback.print_exc()