FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \ 
    && apt-get install -y --no-install-recommends \ 
        curl \ 
        libnss3 \ 
        libatk1.0-0 \ 
        libatk-bridge2.0-0 \ 
        libcups2 \ 
        libdrm2 \ 
        libxkbcommon0 \ 
        libxcomposite1 \ 
        libxdamage1 \ 
        libxfixes3 \ 
        libxrandr2 \ 
        libgbm1 \ 
        libpango-1.0-0 \ 
        libasound2 \ 
        fonts-liberation \ 
        libappindicator3-1 \ 
        libatk-bridge2.0-0 \ 
        wget \ 
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium

COPY app ./app

VOLUME ["/data"]
ENV DATA_DIR=/data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
