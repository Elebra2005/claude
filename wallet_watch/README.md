# wallet-watch — отчёт о балансе крипто-кошельков в Telegram

Каждые 30 минут считает стоимость кошельков (Arbitrum / Solana / Starknet)
по публичным RPC + ценам CoinGecko, плюс баланс на бирже Bybit по API и присылает в личку, если сумма
изменилась больше чем на `min_change_usd`. При первом запуске сразу
присылает стартовый баланс с разбивкой по монетам.

## Что нужно

1. **Отдельный бот** в [@BotFather](https://t.me/BotFather) → `/newbot` → токен.
   Не используйте токен `remna-sales-bot`: этот бот только отправляет
   сообщения, но `get_chat_id.py` читает `getUpdates` и «съест» апдейты
   боевого бота.
2. Напишите новому боту `/start` (бот не может написать первым).
3. Адреса кошельков.
4. Для Bybit — API-ключ **только на чтение** (см. ниже).

## Bybit

Адрес депозита Bybit не подходит: биржа сразу переводит пришедшие монеты в
свои общие кошельки, и по адресу в блокчейне будет $0. Баланс берётся
через API.

1. bybit.com → аватар → **API** → **Create New Key** → **System-generated API Keys**.
2. Права: **Read-Only**. Торговлю, вывод и переводы НЕ включать.
3. Если у сервера постоянный IP, укажите его в IP-ограничении, так ключ
   не сработает ни с какого другого адреса. Без привязки к IP ключ
   с правами только на чтение действует 90 дней.
4. В `.env`: `BYBIT_API_KEY=...` и `BYBIT_API_SECRET=...`
5. В `config.yaml` в `wallets:` добавьте:
   ```yaml
   - chain: bybit
     label: "Bybit"
   ```

Учитываются единый торговый аккаунт, финансовый аккаунт и Bybit Earn
(гибкие сбережения, ончейн-стейкинг). Монеты, для которых на споте Bybit
нет пары к USDT, не оцениваются.

## Развёртывание на сервере (Docker)

```bash
cd /root && git clone https://github.com/elebra2005/claude.git wallet-src \
  || (cd /root/wallet-src && git pull origin claude/clever-lovelace-vh1klo)
cd /root/wallet-src && git checkout claude/clever-lovelace-vh1klo
cd wallet_watch

cp .env.example .env               # вписать TELEGRAM_BOT_TOKEN=...
cp config.example.yaml config.yaml

# узнать chat_id (после /start боту)
docker compose run --rm wallet-watch python get_chat_id.py

nano config.yaml                   # вписать telegram_chat_id и адреса, лишние кошельки удалить

docker compose up -d --build
docker logs -f wallet-watch
```

Состояние (прошлые балансы, просканированные блоки) хранится в
`./data/state.db` — переживает перезапуск и пересборку.

## Изменить кошельки / настройки

```bash
nano config.yaml && docker compose restart wallet-watch
```

## Без Docker

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m bot
```

## Ограничения

- Первая проверка Starknet-кошелька может идти несколько минут: сканируется
  вся история переводов. Дальше сканируются только новые блоки.
- DeFi-позиции, которые не выдают токен на кошелёк (часть лендингов/стейкинга),
  не видны. Исключения: заблокированный JUP в Jupiter DAO и делегированный STRK
  (`starknet_delegation_pool`). Если нужно видеть всё, используйте `source: debank` (платно).
- Из EVM-сетей поддержан только Arbitrum. Для другой сети нужно поменять
  `ARBITRUM_RPC` в `bot/wallet_watch.py`.
