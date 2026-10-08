FROM python:3.11-slim

# Instalar Chromium y dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CHROME_BIN=/usr/bin/chromium
ENV DISPLAY=:99
ENV PORT=10000
EXPOSE 10000


CMD ["python", "main.py"]

