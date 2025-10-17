FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libexpat1 \
        libffi8 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnss3 \
        libpci3 \
        libpango-1.0-0 \
        libpixman-1-0 \
        libpng16-16 \
        libwayland-client0 \
        libwayland-server0 \
        libx11-6 \
        libx11-xcb1 \
        libxcb-dri3-0 \
        libxcb1 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libxrender1 \
        libxshmfence1 \
        libxss1 \
        libxtst6 \
        wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

COPY app ./app

VOLUME ["/data"]
ENV DATA_DIR=/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
