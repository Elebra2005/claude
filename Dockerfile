FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Moscow \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rates_bot ./rates_bot

VOLUME ["/data"]

CMD ["python", "-m", "rates_bot"]
