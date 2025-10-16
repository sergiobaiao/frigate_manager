FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY data ./data

ENV PYTHONPATH=/app
ENV TZ=America/Sao_Paulo

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
