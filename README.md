# Frigate Monitor

Aplicação completa para monitorar instâncias do Frigate e gerar alertas automáticos via Telegram.

## Funcionalidades principais

- Monitoramento cíclico (configurável) de múltiplos hosts utilizando navegador headless (Playwright).
- Reavaliação automática após 5 minutos em caso de múltiplas câmeras com falha.
- Coleta e armazenamento dos logs (`go2rtc`, `nginx`, `frigate`) em arquivos individuais por host.
- Envio de notificações ricas (HTML) para Telegram com menções configuráveis e horário em GMT-3.
- Histórico persistente de execuções com indicadores agregados e detalhados por host.
- Interface web para gerenciamento de hosts, parâmetros e visualização de métricas e logs.
- Configurações persistidas em arquivo JSON (`data/config.json`).

## Estrutura do projeto

```
backend/   -> API FastAPI e rotina de monitoramento
frontend/  -> Interface React + Vite
data/      -> Configurações persistentes, histórico e logs
```

## Executando com Docker Compose

```bash
docker-compose up --build
```

Serviços disponíveis:

- API: http://localhost:8000
- Interface web: http://localhost:5173

Os arquivos de configuração, histórico e logs são mapeados para a pasta `./data` no host.

## Variáveis configuráveis pela interface

- Intervalo das verificações.
- Token, chat e usuários mencionados no Telegram.
- Fuso horário (padrão `America/Sao_Paulo`).
- Hosts monitorados (nome, endereço e notas).

## Desenvolvimento local

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Defina `VITE_API_URL` para apontar a API desejada durante o desenvolvimento, caso não esteja usando `localhost:8000`.
