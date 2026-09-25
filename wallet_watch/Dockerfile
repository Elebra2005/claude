FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY get_chat_id.py .

ENV PYTHONUNBUFFERED=1 \
    WALLET_WATCH_CONFIG=/app/config.yaml \
    WALLET_WATCH_DB=/app/data/state.db

CMD ["python", "-m", "bot"]
