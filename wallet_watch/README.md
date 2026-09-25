# wallet-watch — отчёт о балансе крипто-кошельков в Telegram

Каждые 30 минут считает стоимость кошельков (Arbitrum / Solana / Starknet)
по публичным RPC + ценам CoinGecko и присылает в личку, если сумма
изменилась больше чем на `min_change_usd`. При первом запуске сразу
присылает стартовый баланс с разбивкой по монетам.

## Что нужно

1. **Отдельный бот** в [@BotFather](https://t.me/BotFather) → `/newbot` → токен.
   Не используйте токен `remna-sales-bot`: этот бот только отправляет
   сообщения, но `get_chat_id.py` читает `getUpdates` и «съест» апдейты
   боевого бота.
2. Напишите новому боту `/start` (бот не может написать первым).
3. Адреса кошельков.

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
