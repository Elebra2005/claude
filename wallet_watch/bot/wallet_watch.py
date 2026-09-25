"""Личный трекер стоимости кошелька — не связан с публичным каналом.

Отдельный модуль, а не событие в общей ленте: это уведомление для одного
конкретного человека в личку, а не контент для аудитории. Поэтому здесь
свой цикл (30 мин по умолчанию, не привязан к poll_interval_seconds общего
бота) и своя доставка — напрямую в Telegram DM, минуя publishers/
significance/rate_limit, которые спроектированы под канал.

Два источника данных, переключаются в config.yaml -> wallet_watch.source:

  onchain (по умолчанию, бесплатно) — публичный RPC + CoinGecko. Находит
    все токены, когда-либо касавшиеся кошелька, берёт текущий баланс и
    оценивает по CoinGecko. Три сети: Arbitrum и любая другая EVM-сеть
    (через логи Transfer), Solana (через getTokenAccountsByOwner — там
    можно перечислить все токены сразу, без сканирования истории) и
    Starknet (Cairo VM, свой RPC-протокол и свой алгоритм сигнатур —
    starknet_call/starknet_getEvents вместо eth_call/eth_getLogs).
    Не видит DeFi-позиции, которые протокол считает внутри себя без
    выдачи токена на кошелёк (некоторые лендинги) — это именно то, за
    что платят в DeBank.

  debank (платно после 14-дневного триала) — /v1/user/total_balance,
    та же агрегированная цифра, что показывает сайт DeBank, включая
    DeFi-позиции любого вида. Нужен DEBANK_ACCESS_KEY в .env.

ВАЖНО про цены (CoinGecko, бесплатный тариф без ключа): запрос "цена по
адресу контракта" (simple/token_price) режется до 1 адреса за вызов — при
10-15 токенах на кошелёк это гарантированно упирается в лимит запросов в
минуту и часть токенов остаётся без цены. Обходится не ожиданием лимита,
а сменой способа: запрос "цена по ID монеты" (simple/price?ids=a,b,c,...)
принимает сотни ID одним вызовом бесплатно. Поэтому адреса контрактов
сначала сопоставляются с ID через общий список CoinGecko (coins/list,
кэшируется на сутки — список меняется редко), а сами цены запрашиваются
одним пакетным вызовом на кошелёк за цикл, а не по одному на токен.

ВАЖНО про безопасность: у части токенов, которые когда-либо касались
реального кошелька при проверке, обнаружены фишинговые airdrop-скамы —
их символ содержит вредоносные ссылки (например "Visit ... to claim
rewards", "t.me/s/claimarb"), это распространённая атака. Такие токены
не находятся в CoinGecko и поэтому не попадают в оценку стоимости — но
это не единственная защита: имя/символ токена НИКОГДА не попадает в
исходящее сообщение, только агрегированная сумма. Даже если фишинговый
токен где-то получит цену, его название не окажется в вашей личке.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import httpx

from .bybit import total_usd_bybit
from .config import env
from .cosmos import cosmos_amounts
from .store import Store
from .zerion import total_usd_zerion

log = logging.getLogger(__name__)

DEBANK_API = "https://pro-openapi.debank.com/v1/user/total_balance"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# --- бэкенд onchain (бесплатный) ---

ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
# Token-2022: новый стандарт токенов Solana, на нём выпущена часть новых
# монет — их аккаунты лежат под другой программой и без отдельного
# запроса не видны.
SPL_TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS5EPFLZ6ALXBVGvQrmAc4Tb8"
# Цены Jupiter — для монет Solana, которых нет на CoinGecko (свежие токены).
JUPITER_PRICE_API = "https://lite-api.jup.ag/price/v3"
JUPITER_TOKENS_API = "https://lite-api.jup.ag/tokens/v2/search"
JUP_MINT = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
# Jupiter DAO (vote.jup.ag / lock.jup.ag): форк voter-stake-registry, адрес
# и раскладка байт нигде не документированы публично — найдены и проверены
# вручную по реальной позиции (см. docstring _jupiter_locked_amount).
JUPITER_VOTER_PROGRAM = "voTpe3tHQ7AjQHMapgSue2HJFAh2cGsdokqN3XqmVSj"
JUPITER_VOTER_AUTHORITY_OFFSET = 40
JUPITER_DEPOSIT_AMOUNT_OFFSET = 105
COINGECKO_PLATFORM = {"arbitrum": "arbitrum-one", "solana": "solana", "starknet": "starknet"}
NATIVE_COIN_ID = {"arbitrum": "ethereum", "solana": "solana"}
NATIVE_SYMBOL = {"arbitrum": "ETH", "solana": "SOL"}
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BALANCE_OF_SIG = "0x70a08231"
DECIMALS_SIG = "0x313ce567"

# Starknet: Cairo VM, не EVM — свой RPC-протокол (starknet_call/starknet_getEvents,
# не eth_call/eth_getLogs) и свой способ вычисления сигнатур функций/событий
# (starknet_keccak = keccak256 & (2**250-1), а не первые 4 байта keccak, как в EVM).
# Значения ниже сверены живыми вызовами перед деплоем: symbol() у ETH_TOKEN и
# STRK_TOKEN вернул ровно "ETH"/"STRK", TRANSFER_KEY совпал с ключом реального
# события на STRK-контракте.
STARKNET_RPC = "https://starknet-rpc.publicnode.com"
STARKNET_ETH = "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
STARKNET_STRK = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"
STARKNET_NATIVE_COIN_ID = {STARKNET_ETH: "ethereum", STARKNET_STRK: "starknet"}
# pool_member_info_v1(pool_member) -> (reward_address, amount, ...) — вызывается
# на КОНКРЕТНОМ pool-контракте (свой у каждого валидатора/провайдера, например
# у Braavos), а не на общем контракте стейкинга. Единого способа узнать нужный
# pool по одному только адресу кошелька нет (не индексируется публично) —
# адрес пула для конкретного делегатора указывается в config.yaml вручную,
# найден трассировкой реальной транзакции делегирования.
STARKNET_POOL_MEMBER_INFO_SELECTOR = "0x2568ae59c943c8367eb5c7690be688385a1100f8ee3d14db8e693dec9aec585"
STARKNET_BALANCE_OF_SELECTOR = "0x2e4263afad30923c891518314c3c95dbe830a16874e8abc5777a9a20b54c76e"
STARKNET_DECIMALS_SELECTOR = "0x4c4fb1ab068f6039d5780c68dd0fa2f8742cceb3426d19667778ca7f3518a9"
STARKNET_TRANSFER_KEY = "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"
# Публичная нода обрывает starknet_getEvents с ошибкой брокера примерно
# после 30с — замерено: диапазон в 1М блоков занимает ~9.5с, поэтому режем
# полную историю (на момент внедрения — больше 15М блоков) на чанки этого
# размера вместо одного запроса genesis→head, который не проходит целиком.
STARKNET_EVENT_CHUNK_BLOCKS = 1_500_000

COINGECKO_MAP_TTL_S = 24 * 3600  # список адрес->ID меняется редко, обновляем раз в сутки


async def _get_with_backoff(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    """GET с одной попыткой пережить 429: ждём Retry-After и повторяем один
    раз. Бесплатный тариф CoinGecko на практике оказался строже, чем
    документировано — без этого случайный всплеск лимита на единственном
    пакетном запросе цен обнулял бы всю оценку кошелька за цикл.
    """
    resp = None
    for attempt in range(2):
        resp = await client.get(url, params=params)
        if resp.status_code != 429:
            return resp
        if attempt == 0:
            wait_s = min(float(resp.headers.get("retry-after", 30)), 90)
            log.debug("wallet_watch: 429 от CoinGecko, жду %.0fс и пробую ещё раз", wait_s)
            await asyncio.sleep(wait_s)
    return resp


async def _coingecko_address_map(client: httpx.AsyncClient, store: Store) -> dict[str, dict[str, dict]]:
    """Адрес контракта -> {id, symbol} монеты на CoinGecko, отдельно по сети.

    id нужен для запроса цены, symbol — только для читаемой подписи в личном
    уведомлении (разбивка по монетам). Кэшируется в Store на сутки: список
    тысяч монет меняется редко, а получать его заново каждый 30-минутный
    цикл незачем — это и есть единственный "дорогой" запрос, всё остальное
    ценообразование потом идёт одним пакетным вызовом по уже известным ID.
    """
    # _v2 в ключе: формат кэша поменялся (раньше значение — просто id
    # строкой, теперь {"id","symbol"}) — старый кэш с другим форматом не
    # должен тихо приводить к падению на новом коде.
    cached_ts = store.get_cursor("coingecko_map_ts_v2")
    cached_data = store.get_cursor("coingecko_map_data_v2")
    if cached_ts and cached_data and time.time() - float(cached_ts) < COINGECKO_MAP_TTL_S:
        return json.loads(cached_data)

    wanted = set(COINGECKO_PLATFORM.values())
    mapping: dict[str, dict[str, dict]] = {}
    try:
        resp = await _get_with_backoff(
            client, "https://api.coingecko.com/api/v3/coins/list", {"include_platform": "true"}
        )
        resp.raise_for_status()
        for coin in resp.json():
            for platform, addr in (coin.get("platforms") or {}).items():
                if platform in wanted and addr:
                    mapping.setdefault(platform, {})[addr.lower()] = {
                        "id": coin["id"], "symbol": (coin.get("symbol") or coin["id"]).upper(),
                    }
        store.set_cursor("coingecko_map_data_v2", json.dumps(mapping))
        store.set_cursor("coingecko_map_ts_v2", str(time.time()))
        return mapping
    except Exception as exc:
        if cached_data:
            log.info("wallet_watch: не удалось обновить список CoinGecko (%s), использую старый кэш", exc)
            return json.loads(cached_data)
        log.warning("wallet_watch: список CoinGecko недоступен и кэша нет: %s", exc)
        return {}


async def _prices_by_ids(client: httpx.AsyncClient, ids: set[str]) -> dict[str, float]:
    """Цены пакетом по ID монет — в отличие от поиска по адресу контракта,
    здесь бесплатный тариф не режет до одного элемента за запрос."""
    if not ids:
        return {}
    try:
        resp = await _get_with_backoff(
            client,
            "https://api.coingecko.com/api/v3/simple/price",
            {"ids": ",".join(sorted(ids)), "vs_currencies": "usd"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {coin_id: info["usd"] for coin_id, info in data.items() if "usd" in info}
    except Exception as exc:
        log.warning("wallet_watch: пакетный запрос цен CoinGecko не удался: %s", exc)
        return {}


async def _rpc(client: httpx.AsyncClient, url: str, method: str, params: list):
    resp = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "RPC error"))
    return data["result"]


async def _discover_tokens(client: httpx.AsyncClient, rpc_url: str, address: str, store: Store, cache_key: str) -> set[str]:
    """Контракты токенов, когда-либо касавшихся адреса — сканируется инкрементально.

    Полный скан истории — дорогая операция; после первого прохода
    запоминаем последний просмотренный блок и на следующих циклах
    смотрим только новые блоки, а не всю историю заново.
    """
    topic_addr = "0x" + "0" * 24 + address[2:].lower()
    known = store.get_snapshot(cache_key) or set()
    last_block = store.get_cursor(f"{cache_key}_scanned_block")

    try:
        head = int(await _rpc(client, rpc_url, "eth_blockNumber", []), 16)
        from_block = int(last_block) + 1 if last_block else 0
        if from_block > head:
            return known

        incoming = await _rpc(client, rpc_url, "eth_getLogs", [
            {"fromBlock": hex(from_block), "toBlock": hex(head), "topics": [TRANSFER_TOPIC, None, topic_addr]}
        ])
        outgoing = await _rpc(client, rpc_url, "eth_getLogs", [
            {"fromBlock": hex(from_block), "toBlock": hex(head), "topics": [TRANSFER_TOPIC, topic_addr, None]}
        ])
        new_tokens = {log_entry["address"].lower() for log_entry in incoming + outgoing}
        known = known | new_tokens
        store.save_snapshot(cache_key, known)
        store.set_cursor(f"{cache_key}_scanned_block", str(head))
    except Exception as exc:
        # Курсор не сдвинулся — пропущенные блоки досканируются на следующей проверке.
        log.info("wallet_watch: скан токенов кошелька не удался (%s), использую уже известные", exc)

    return known


async def _token_balance(client: httpx.AsyncClient, rpc_url: str, token: str, address: str) -> float | None:
    """Текущий баланс токена в нормальных единицах. None — если контракт
    не отвечает как стандартный ERC-20 (например, это NFT — та же сигнатура
    события Transfer, но balanceOf/decimals ведут себя иначе)."""
    data = BALANCE_OF_SIG + "0" * 24 + address[2:].lower()
    try:
        raw = await _rpc(client, rpc_url, "eth_call", [{"to": token, "data": data}, "latest"])
        balance = int(raw, 16) if raw and raw != "0x" else 0
        if balance == 0:
            return None
        dec_raw = await _rpc(client, rpc_url, "eth_call", [{"to": token, "data": DECIMALS_SIG}, "latest"])
        decimals = int(dec_raw, 16)
        return balance / (10 ** decimals)
    except Exception:
        return None


async def _total_usd_evm_onchain(client: httpx.AsyncClient, chain: str, address: str, store: Store, cache_key: str) -> dict[str, dict] | None:
    """EVM-сети (Arbitrum и любая другая, где включён балансOf/logs).

    Токены обнаруживаются через историю логов Transfer — на EVM нет
    прямого способа перечислить "все токены на адресе", в отличие от Solana.

    Возвращает разбивку {coin_id: {"symbol", "usd"}} — не просто сумму,
    чтобы личное уведомление могло показать изменение по каждой монете.
    """
    rpc_url = {"arbitrum": ARBITRUM_RPC}.get(chain)
    platform = COINGECKO_PLATFORM.get(chain)
    if not rpc_url or not platform:
        log.warning("wallet_watch: сеть %s не поддержана бэкендом onchain (EVM)", chain)
        return None

    tokens = await _discover_tokens(client, rpc_url, address, store, cache_key)
    balances: dict[str, float] = {}
    for token in tokens:
        bal = await _token_balance(client, rpc_url, token, address)
        if bal:
            balances[token] = bal

    native_amount = 0.0
    try:
        native_wei = int(await _rpc(client, rpc_url, "eth_getBalance", [address, "latest"]), 16)
        native_amount = native_wei / 1e18
    except Exception as exc:
        log.warning("wallet_watch: нативный баланс недоступен: %s", exc)
    native_id = NATIVE_COIN_ID.get(chain)

    addr_map = (await _coingecko_address_map(client, store)).get(platform, {})
    entry_by_token = {token: addr_map[token] for token in balances if token in addr_map}
    needed_ids = {e["id"] for e in entry_by_token.values()}
    if native_id and native_amount:
        needed_ids.add(native_id)
    prices = await _prices_by_ids(client, needed_ids)

    breakdown: dict[str, dict] = {}
    if native_id and native_amount:
        price = prices.get(native_id)
        if price:
            breakdown[native_id] = {"symbol": NATIVE_SYMBOL.get(chain, native_id.upper()), "usd": native_amount * price}
    for token, amount in balances.items():
        # Токен не найден в списке CoinGecko вообще (в т.ч. фишинговые
        # airdrop-скамы, обнаруженные на практике) — не оцениваем, не называем.
        entry = entry_by_token.get(token)
        price = prices.get(entry["id"]) if entry else None
        if entry and price:
            breakdown[entry["id"]] = {"symbol": entry["symbol"], "usd": amount * price}

    return breakdown


async def _jupiter_locked_amount(client: httpx.AsyncClient, address: str) -> float:
    """JUP, заблокированный в голосовании Jupiter DAO — это позиция внутри
    их программы, не токен на кошельке, обычный скан токенов её не видит.

    Программа (voTpe3t...) и раскладка байт не документированы Jupiter
    публично — установлены вручную сравнением с реальной позицией:
    искали через getProgramAccounts с фильтром по voter_authority (адрес
    кошелька, offset 40 — 8 байт дискриминатора Anchor + 32 байта
    registrar), нашли аккаунт "Voter", разобрали побайтово и подобрали
    поле amount_deposited_native первого слота депозита (offset 105, u64,
    6 знаков как у самого JUP) — сумма по текущему курсу совпала с суммой
    на скриншоте кошелька день-в-день. Учитывается только первый слот:
    у аккаунта есть слоты под несколько депозитов, но надёжного способа
    отличить активный от освобождённого/устаревшего в этом форке не нашли
    (стандартный флаг is_used в данных нулевой даже у активного слота).
    Покрывает типичный случай одной активной блокировки.
    """
    try:
        resp = await client.post(
            SOLANA_RPC,
            json={
                "jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts",
                "params": [JUPITER_VOTER_PROGRAM, {
                    "encoding": "base64",
                    "filters": [{"memcmp": {"offset": JUPITER_VOTER_AUTHORITY_OFFSET, "bytes": address}}],
                }],
            },
        )
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        accounts = data["result"]
        if not accounts:
            return 0.0
        raw = base64.b64decode(accounts[0]["account"]["data"][0])
        if len(raw) < JUPITER_DEPOSIT_AMOUNT_OFFSET + 8:
            return 0.0
        amount = int.from_bytes(raw[JUPITER_DEPOSIT_AMOUNT_OFFSET:JUPITER_DEPOSIT_AMOUNT_OFFSET + 8], "little")
        return amount / 1e6
    except Exception as exc:
        log.warning("wallet_watch: заблокированный JUP недоступен: %s", exc)
        return 0.0


async def _total_usd_solana_onchain(client: httpx.AsyncClient, address: str, store: Store) -> dict[str, dict] | None:
    """Solana — проще, чем EVM: getTokenAccountsByOwner отдаёт ВСЕ текущие
    токены на адресе одним вызовом, историю сканировать не нужно вообще.

    Возвращает разбивку {coin_id: {"symbol", "usd"}}, как и EVM-версия."""
    sol_amount = 0.0
    try:
        resp = await client.post(
            SOLANA_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]},
        )
        lamports = resp.json().get("result", {}).get("value") or 0
        sol_amount = lamports / 1e9
    except Exception as exc:
        log.warning("wallet_watch: нативный баланс SOL недоступен: %s", exc)

    accounts: list[dict] = []
    for program in (SPL_TOKEN_PROGRAM, SPL_TOKEN_2022_PROGRAM):
        try:
            resp = await client.post(
                SOLANA_RPC,
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                    "params": [address, {"programId": program}, {"encoding": "jsonParsed"}],
                },
            )
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            accounts += data["result"]["value"]
        except Exception as exc:
            log.warning("wallet_watch: список SPL-токенов (%s) недоступен: %s", program[:8], exc)

    balances: dict[str, float] = {}
    for acc in accounts:
        info = acc["account"]["data"]["parsed"]["info"]
        amount = float(info["tokenAmount"]["uiAmountString"] or 0)
        if amount > 0:
            balances[info["mint"]] = balances.get(info["mint"], 0.0) + amount

    # JUP, заблокированный в голосовании Jupiter DAO — DeFi-позиция в чужом
    # контракте, getTokenAccountsByOwner её не видит (токен не лежит на
    # кошельке). Складываем поверх обычного баланса JUP, если он есть —
    # дальше по пайплайну это один и тот же коин с одной ценой.
    locked_jup = await _jupiter_locked_amount(client, address)
    if locked_jup:
        balances[JUP_MINT] = balances.get(JUP_MINT, 0.0) + locked_jup

    # Solana-адреса (base58) регистрозависимы — приводить к .lower() нельзя,
    # поэтому сопоставление с картой CoinGecko ищет по .lower() отдельно
    # (сам список CoinGecko отдаёт адреса в нижнем регистре).
    addr_map = (await _coingecko_address_map(client, store)).get("solana", {})
    entry_by_mint = {mint: addr_map[mint.lower()] for mint in balances if mint.lower() in addr_map}
    needed_ids = {e["id"] for e in entry_by_mint.values()}
    if sol_amount:
        needed_ids.add("solana")
    prices = await _prices_by_ids(client, needed_ids)

    breakdown: dict[str, dict] = {}
    if sol_amount:
        price = prices.get("solana")
        if price:
            breakdown["solana"] = {"symbol": "SOL", "usd": sol_amount * price}
    unpriced: dict[str, float] = {}
    for mint, amount in balances.items():
        entry = entry_by_mint.get(mint)
        price = prices.get(entry["id"]) if entry else None
        if entry and price:
            breakdown[entry["id"]] = {"symbol": entry["symbol"], "usd": amount * price}
        else:
            unpriced[mint] = amount

    # Нет на CoinGecko — пробуем цену Jupiter (там есть почти всё, что
    # торгуется на Solana). Мусорные аирдропы без ликвидности цены не
    # имеют или стоят копейки и отсекаются порогом min_coin_usd.
    if unpriced:
        for mint, (symbol, usd) in (await _jupiter_valuation(client, unpriced)).items():
            breakdown[f"sol:{mint}"] = {"symbol": symbol, "usd": usd}

    return breakdown


def _safe_symbol(symbol: str, fallback: str) -> str:
    """Символ токена из внешнего источника — только буквы/цифры, коротко.

    У фишинговых токенов в символе бывают ссылки ("t.me/...", "Visit ...");
    так они не попадут в сообщение в виде ссылки.
    """
    clean = "".join(ch for ch in (symbol or "") if ch.isalnum())[:12]
    return clean.upper() or fallback


async def _jupiter_valuation(client: httpx.AsyncClient, amounts: dict[str, float]) -> dict[str, tuple[str, float]]:
    """{mint: (символ, usd)} по ценам Jupiter для монет без цены на CoinGecko."""
    mints = list(amounts)[:50]
    try:
        resp = await client.get(JUPITER_PRICE_API, params={"ids": ",".join(mints)})
        resp.raise_for_status()
        data = resp.json()
        data = data.get("data", data)  # v3 — {mint: {...}}, v2 — {"data": {mint: {...}}}
        prices = {
            mint: float(info.get("usdPrice") or info.get("price") or 0)
            for mint, info in data.items() if isinstance(info, dict)
        }
    except Exception as exc:
        log.warning("wallet_watch: цены Jupiter недоступны: %s", exc)
        return {}

    priced = {m: amounts[m] * p for m, p in prices.items() if p and m in amounts}
    if not priced:
        return {}
    symbols: dict[str, str] = {}
    try:
        resp = await client.get(JUPITER_TOKENS_API, params={"query": ",".join(priced)})
        resp.raise_for_status()
        for t in resp.json():
            symbols[t.get("id") or t.get("address")] = t.get("symbol") or ""
    except Exception as exc:
        log.info("wallet_watch: символы токенов Jupiter недоступны: %s", exc)
    return {m: (_safe_symbol(symbols.get(m, ""), m[:4] + "…"), usd) for m, usd in priced.items()}


# --- бэкенд onchain: Starknet ---

async def _starknet_call(client: httpx.AsyncClient, contract: str, selector: str, calldata: list[str]) -> list[str]:
    return await _rpc(client, STARKNET_RPC, "starknet_call", [
        {"contract_address": contract, "entry_point_selector": selector, "calldata": calldata}, "latest"
    ])


async def _starknet_token_balance(client: httpx.AsyncClient, token: str, address: str) -> float | None:
    """Как и на EVM: None, если контракт не отвечает как стандартный токен."""
    try:
        low, high = await _starknet_call(client, token, STARKNET_BALANCE_OF_SELECTOR, [address])
        balance = int(low, 16) + (int(high, 16) << 128)
        if balance == 0:
            return None
        dec_raw = await _starknet_call(client, token, STARKNET_DECIMALS_SELECTOR, [])
        decimals = int(dec_raw[0], 16)
        return balance / (10 ** decimals)
    except Exception:
        return None


async def _starknet_get_events(client: httpx.AsyncClient, keys: list, from_block: int, to_block: int) -> list[dict]:
    """Все события Cairo в диапазоне блоков, с пагинацией continuation_token."""
    events: list[dict] = []
    continuation = None
    while True:
        params = {
            "from_block": {"block_number": from_block},
            "to_block": {"block_number": to_block},
            "keys": keys,
            "chunk_size": 1000,
        }
        if continuation:
            params["continuation_token"] = continuation
        result = await _rpc(client, STARKNET_RPC, "starknet_getEvents", [params])
        events.extend(result["events"])
        continuation = result.get("continuation_token")
        if not continuation:
            break
    return events


async def _starknet_scan_transfers(client: httpx.AsyncClient, address: str, from_block: int, to_block: int) -> list[dict]:
    """Режем диапазон на чанки — публичная нода обрывает запрос примерно
    после 30с, а вся история Starknet (полная перепроверка при первом
    запуске) намного шире одного такого чанка."""
    events: list[dict] = []
    start = from_block
    while start <= to_block:
        end = min(start + STARKNET_EVENT_CHUNK_BLOCKS - 1, to_block)
        events += await _starknet_get_events(client, [[STARKNET_TRANSFER_KEY], [], [address]], start, end)
        events += await _starknet_get_events(client, [[STARKNET_TRANSFER_KEY], [address], []], start, end)
        start = end + 1
    return events


def _felt(value: str) -> str:
    """Адрес Starknet в одном виде: RPC отдаёт их то с ведущими нулями, то
    без — без нормализации один и тот же токен считался бы дважды."""
    return f"0x{int(value, 16):064x}"


async def _discover_tokens_starknet(client: httpx.AsyncClient, address: str, store: Store, cache_key: str) -> set[str]:
    """Аналог _discover_tokens для EVM, но через starknet_getEvents —
    инкрементально, тот же принцип (запоминаем последний просмотренный блок).

    Заодно запоминает получателей исходящих переводов STRK — среди них
    пул стейкинга, если STRK делегирован (см. _starknet_detect_pools)."""
    known = store.get_snapshot(cache_key) or set()
    last_block = store.get_cursor(f"{cache_key}_scanned_block")
    strk_out_key = f"{cache_key}_strk_out"

    try:
        head = await _rpc(client, STARKNET_RPC, "starknet_blockNumber", [])
        from_block = int(last_block) + 1 if last_block else 0
        if from_block > head:
            return {_felt(t) for t in known}

        events = await _starknet_scan_transfers(client, address, from_block, head)
        new_tokens = {_felt(e["from_address"]) for e in events}
        known = {_felt(t) for t in known} | new_tokens
        me = int(address, 16)
        strk_out = {
            _felt(e["keys"][2]) for e in events
            if _felt(e["from_address"]) == STARKNET_STRK and len(e.get("keys", [])) >= 3
            and int(e["keys"][1], 16) == me
        }
        if strk_out:
            store.save_snapshot(strk_out_key, (store.get_snapshot(strk_out_key) or set()) | strk_out)
        store.save_snapshot(cache_key, known)
        store.set_cursor(f"{cache_key}_scanned_block", str(head))
    except Exception as exc:
        log.info("wallet_watch: скан токенов Starknet не удался (%s), использую уже известные", exc)

    return {_felt(t) for t in known}


STARKNET_NATIVE_SYMBOL = {STARKNET_ETH: "ETH", STARKNET_STRK: "STRK"}


async def _starknet_delegated_amount(client: httpx.AsyncClient, pool_address: str, member_address: str) -> float:
    """STRK, делегированный в пул стейкинга — DeFi-позиция в отдельном
    контракте (свой у каждого валидатора/провайдера), balanceOf STRK её не
    видит. pool_address — из config.yaml (wallet_watch.wallets[].
    starknet_delegation_pool), найден трассировкой транзакции делегирования,
    вызов сверен вживую с реальной позицией ($119.07 на 2.990 STRK)."""
    try:
        result = await _starknet_call(client, pool_address, STARKNET_POOL_MEMBER_INFO_SELECTOR, [member_address])
        # pool_member_info_v1 -> (reward_address, amount_lo, amount_hi, ...) —
        # amount представлен как u128, здесь укладывается в одно слово (lo).
        amount = int(result[1], 16)
        return amount / 1e18
    except RuntimeError as exc:
        # Ошибка самого контракта (не участник пула / вышел из него) — это
        # честный ноль, а не сбой сети.
        log.debug("wallet_watch: %s — не пул или нет делегирования: %s", pool_address, exc)
        return 0.0
    except Exception as exc:
        log.warning("wallet_watch: делегированный STRK недоступен: %s", exc)
        return 0.0


async def _starknet_detect_pools(client: httpx.AsyncClient, address: str, store: Store, cache_key: str) -> set[str]:
    """Пулы стейкинга, куда кошелёк делегировал STRK, — без ручного ввода.

    При делегировании STRK уходит с кошелька на контракт пула, поэтому пул
    есть среди получателей исходящих переводов STRK. Каждого нового
    получателя один раз спрашиваем pool_member_info_v1: ответил — это пул
    (запоминаем), ошибка контракта — не пул (тоже запоминаем, больше не
    спрашиваем)."""
    pools_key, checked_key = f"{cache_key}_pools", f"{cache_key}_pool_checked"
    pools = store.get_snapshot(pools_key) or set()
    checked = store.get_snapshot(checked_key) or set()
    candidates = (store.get_snapshot(f"{cache_key}_strk_out") or set()) - checked - pools
    for candidate in candidates:
        try:
            await _starknet_call(client, candidate, STARKNET_POOL_MEMBER_INFO_SELECTOR, [address])
            pools.add(candidate)
            log.info("wallet_watch: найден пул стейкинга STRK %s", candidate)
        except RuntimeError:
            checked.add(candidate)
        except Exception as exc:
            log.info("wallet_watch: проверка пула %s отложена: %s", candidate, exc)
    store.save_snapshot(pools_key, pools)
    store.save_snapshot(checked_key, checked)
    return pools


async def _total_usd_starknet_onchain(
    client: httpx.AsyncClient, address: str, store: Store, cache_key: str, delegation_pool: str | None = None
) -> dict[str, dict] | None:
    tokens = await _discover_tokens_starknet(client, address, store, cache_key)
    tokens |= {STARKNET_ETH, STARKNET_STRK}  # системные токены сети есть всегда, проверяем их напрямую

    balances: dict[str, float] = {}
    for token in tokens:
        bal = await _starknet_token_balance(client, token, address)
        if bal:
            balances[token] = bal

    pools = await _starknet_detect_pools(client, address, store, cache_key)
    if delegation_pool:
        pools.add(_felt(delegation_pool))
    for pool in pools:
        delegated = await _starknet_delegated_amount(client, pool, address)
        if delegated:
            balances[STARKNET_STRK] = balances.get(STARKNET_STRK, 0.0) + delegated

    raw_map = (await _coingecko_address_map(client, store)).get("starknet", {})
    addr_map = {}
    for k, v in raw_map.items():
        try:
            addr_map[_felt(k)] = v
        except ValueError:
            continue
    id_by_token = dict(STARKNET_NATIVE_COIN_ID)
    id_by_token.update({token: addr_map[token.lower()]["id"] for token in balances if token.lower() in addr_map})
    symbol_by_token = dict(STARKNET_NATIVE_SYMBOL)
    symbol_by_token.update({token: addr_map[token.lower()]["symbol"] for token in balances if token.lower() in addr_map})
    needed_ids = {id_by_token[t] for t in balances if t in id_by_token}
    prices = await _prices_by_ids(client, needed_ids)

    breakdown: dict[str, dict] = {}
    for token, amount in balances.items():
        coin_id = id_by_token.get(token)
        price = prices.get(coin_id)
        if coin_id and price:
            breakdown[coin_id] = {"symbol": symbol_by_token.get(token, coin_id.upper()), "usd": amount * price}
    return breakdown


# --- бэкенд debank (платный) ---

async def _total_usd_debank(client: httpx.AsyncClient, access_key: str, address: str) -> float | None:
    try:
        resp = await client.get(
            DEBANK_API,
            params={"id": address},
            headers={"AccessKey": access_key, "accept": "application/json"},
        )
        resp.raise_for_status()
        return float(resp.json()["total_usd_value"])
    except Exception as exc:
        log.warning("DeBank: не удалось получить баланс %s: %s", address, exc)
        return None


# --- общее ---

async def _send_dm(client: httpx.AsyncClient, token: str, chat_id: str, text: str) -> None:
    try:
        resp = await client.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text},
        )
        if resp.status_code != 200:
            log.error("Личное уведомление не доставлено: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        log.error("Личное уведомление: ошибка отправки: %s", exc)


def _usd(value: float) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def _format_change(label: str, address: str, previous: float, current: float) -> str:
    delta = current - previous
    pct = (delta / previous * 100) if previous else 0.0
    arrow = "📈" if delta > 0 else "📉" if delta < 0 else "➖"
    short_addr = f"{address[:6]}…{address[-4:]}"
    return (
        f"{arrow} {label or short_addr}\n"
        f"{_usd(previous)} → {_usd(current)} ({pct:+.2f}%)\n"
        f"Изменение: {'+' if delta >= 0 else ''}{delta:,.2f}$"
    )


def _format_coin_line(symbol: str, previous: float, current: float) -> str:
    delta = current - previous
    arrow = "📈" if delta > 0.005 else "📉" if delta < -0.005 else "➖"
    pct = f", {delta / abs(previous) * 100:+.2f}%" if previous else ""
    return f"{arrow} {symbol}: {_usd(current)} ({'+' if delta >= 0 else ''}{delta:,.2f}${pct})"


def _format_total_line(previous: float | None, current: float) -> str:
    if previous is None:
        return f"💰 Итого по всем кошелькам: {_usd(current)}"
    delta = current - previous
    pct = (delta / previous * 100) if previous else 0.0
    arrow = "📈" if delta > 0 else "📉" if delta < 0 else "➖"
    return (
        f"{arrow} Итого по всем кошелькам\n"
        f"{_usd(previous)} → {_usd(current)} ({pct:+.2f}%)\n"
        f"Изменение: {'+' if delta >= 0 else ''}{delta:,.2f}$"
    )


async def _fetch_wallet(
    client: httpx.AsyncClient, w: dict, chain: str, address: str, source: str, debank_key: str | None, store: Store
) -> tuple[dict[str, dict] | None, float | None]:
    """(разбивка по монетам, сумма) — сумма только у source=debank."""
    breakdown: dict[str, dict] | None = None
    current: float | None = None
    if chain == "bybit":
        breakdown = await total_usd_bybit(client)
    elif chain == "zerion":
        breakdown = await total_usd_zerion(client, address)
    elif chain == "cosmos":
        amounts = await cosmos_amounts(client, w)
        prices = await _prices_by_ids(client, set(amounts))
        breakdown = {
            cid: {"symbol": sym, "usd": qty * prices[cid]}
            for cid, (sym, qty) in amounts.items() if prices.get(cid)
        }
    elif source == "debank":
        current = await _total_usd_debank(client, debank_key, address)
    elif chain == "solana":
        breakdown = await _total_usd_solana_onchain(client, address, store)
    elif chain == "starknet":
        cache_key = f"wallet_tokens_starknet_{address.lower()}"
        pool = w.get("starknet_delegation_pool")
        breakdown = await _total_usd_starknet_onchain(client, address, store, cache_key, pool)
    else:
        cache_key = f"wallet_tokens_{chain}_{address.lower()}"
        breakdown = await _total_usd_evm_onchain(client, chain, address, store, cache_key)

    return breakdown, current


class _WarningCounter(logging.Handler):
    """Считает предупреждения, пока считается один кошелёк.

    Бэкенды при сбое сети не падают, а пишут предупреждение и возвращают
    то, что успели получить, — это заниженная сумма, и без такой проверки
    сбой публичного RPC выглядел бы как падение баланса (а на следующей
    проверке — как такой же рост).
    """

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


async def check_once(cfg: dict, store: Store) -> None:
    """Один проход по всем отслеживаемым кошелькам."""
    wc = cfg.get("wallet_watch", {})
    source = wc.get("source", "onchain")
    bot_token = env("TELEGRAM_BOT_TOKEN")
    chat_id = wc.get("telegram_chat_id")
    debank_key = env("DEBANK_ACCESS_KEY")

    if not bot_token or not chat_id:
        log.warning(
            "wallet_watch включён, но некому слать: нужен TELEGRAM_BOT_TOKEN "
            "и wallet_watch.telegram_chat_id (напишите боту /start, чтобы узнать chat_id)"
        )
        return
    if source == "debank" and not debank_key:
        log.warning("wallet_watch.source=debank, но DEBANK_ACCESS_KEY не задан в .env")
        return

    wallets = wc.get("wallets") or []
    # Позиции дешевле этого — пыль (мусорные аирдропы, копейки), не стоят
    # отдельной строки в личке и не считаются "монетой на кошельке".
    min_coin_usd = wc.get("min_coin_usd", 1.0)
    # Отчёт на каждой проверке (по всем кошелькам, даже без изменений),
    # а не только когда сумма сдвинулась больше чем на min_change_usd.
    report_every_check = wc.get("report_every_check", True)
    sections: list[str] = []
    failed: list[str] = []
    all_current: dict[str, float] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for w in wallets:
            chain = w.get("chain", "arbitrum")
            # У биржи нет ончейн-адреса — "адрес" здесь только ключ для
            # хранения прошлых значений.
            address = w.get("address") or ("bybit" if chain == "bybit" else None)
            label = w.get("label") or ""
            if not address:
                continue

            breakdown: dict[str, dict] | None = None
            current: float | None = None
            warnings = _WarningCounter()
            pkg_log = logging.getLogger(__package__)
            pkg_log.addHandler(warnings)
            try:
                breakdown, current = await _fetch_wallet(client, w, chain, address, source, debank_key, store)
            finally:
                pkg_log.removeHandler(warnings)

            if breakdown is not None:
                # abs: займы в лендингах идут с минусом, но крупный долг — не пыль.
                breakdown = {cid: e for cid, e in breakdown.items() if abs(e["usd"]) >= min_coin_usd}
                current = sum(entry["usd"] for entry in breakdown.values())
            cursor_key = f"wallet_value_{address.lower()}"
            previous_raw = store.get_cursor(cursor_key)
            if current is None or warnings.count:
                # Сумма неполная — не сохраняем её и не сравниваем, а в итог
                # берём прошлое значение, чтобы он не "проваливался".
                failed.append(label or address)
                if previous_raw is not None:
                    all_current[address] = float(previous_raw)
                continue
            all_current[address] = current
            store.set_cursor(cursor_key, str(current))

            # Разбивка по монетам хранится отдельно от общей суммы — нужна
            # для построчных изменений в уведомлении (source=debank такой
            # разбивки не даёт, только агрегат — там breakdown_key не пишем).
            breakdown_key = f"wallet_breakdown_{address.lower()}"
            previous_breakdown_raw = store.get_cursor(breakdown_key) if breakdown is not None else None
            if breakdown is not None:
                store.set_cursor(breakdown_key, json.dumps({cid: e["usd"] for cid, e in breakdown.items()}))

            if previous_raw is None:
                # Первый замер — сравнивать не с чем, но сообщаем стартовую
                # сумму, чтобы сразу было видно, что бот работает.
                log.info("wallet_watch: baseline для %s = $%.2f", address, current)
                short_addr = f"{address[:6]}…{address[-4:]}"
                lines = [f"🆕 {label or short_addr}: {_usd(current)}"]
                if breakdown:
                    top = sorted(breakdown.values(), key=lambda e: -e["usd"])
                    lines += [f"  • {e['symbol']}: {_usd(e['usd'])}" for e in top]
                sections.append("\n".join(lines))
                continue

            previous = float(previous_raw)
            # Порог против шума: разница в доли доллара от округления курсов
            # не стоит отдельного сообщения в личку каждые 30 минут.
            min_change_usd = wc.get("min_change_usd", 1.0)
            if abs(current - previous) < min_change_usd and not report_every_check:
                continue

            lines = [_format_change(label, address, previous, current)]
            if breakdown is not None:
                prev_breakdown = json.loads(previous_breakdown_raw) if previous_breakdown_raw else {}
                coin_lines = []
                for coin_id in set(prev_breakdown) | set(breakdown):
                    prev_usd = prev_breakdown.get(coin_id, 0.0)
                    cur_usd = breakdown.get(coin_id, {}).get("usd", 0.0)
                    if abs(cur_usd - prev_usd) < min_change_usd and not report_every_check:
                        continue
                    symbol = breakdown.get(coin_id, {}).get("symbol", coin_id.upper())
                    # В режиме отчёта — по размеру позиции, иначе — по размеру изменения.
                    order = max(cur_usd, prev_usd) if report_every_check else abs(cur_usd - prev_usd)
                    coin_lines.append((order, _format_coin_line(symbol, prev_usd, cur_usd)))
                if coin_lines:
                    coin_lines.sort(key=lambda x: -x[0])
                    lines.append("\nПо монетам:")
                    lines += [line for _, line in coin_lines]

            sections.append("\n".join(lines))

        if not sections:
            return

        # Одно сообщение на все изменившиеся кошельки разом, а не по одному
        # на кошелёк — плюс общий баланс по всем настроенным кошелькам в
        # конце (включая те, что в этом цикле не изменились).
        grand_current = sum(all_current.values())
        grand_prev_raw = store.get_cursor("wallet_watch_grand_total")
        store.set_cursor("wallet_watch_grand_total", str(grand_current))
        grand_previous = float(grand_prev_raw) if grand_prev_raw is not None else None

        tail = [_format_total_line(grand_previous, grand_current)]
        if failed:
            # Иначе пропавший кошелёк выглядел бы как падение итога.
            tail.append(
                "⚠️ Не удалось посчитать (сеть не ответила): " + ", ".join(failed)
                + "\nВ итоге для них — сумма с прошлой проверки."
            )
        text = "\n\n".join(sections + tail)
        await _send_dm(client, bot_token, chat_id, text)
        log.info("wallet_watch: отправлено уведомление (%d кошельков изменилось)", len(sections))


async def run_wallet_watch(cfg: dict, store: Store) -> None:
    """Независимый цикл — своя частота опроса, не связанная с основным ботом."""
    interval = max(int((cfg.get("wallet_watch") or {}).get("interval_minutes", 30)), 1) * 60
    log.info("wallet_watch: запущен, интервал %d мин", interval // 60)
    while True:
        try:
            await check_once(cfg, store)
        except Exception as exc:
            log.error("wallet_watch: непредвиденная ошибка цикла: %s", exc)
        await asyncio.sleep(interval)
