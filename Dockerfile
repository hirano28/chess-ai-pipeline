FROM python:3.11-slim

# Stockfish via apt: no Debian slim o binário fica em /usr/games/stockfish
# (mesmo caminho já validado no workflow do GitHub Actions).
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

ENV STOCKFISH_PATH=/usr/games/stockfish

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY docs/ ./docs/

EXPOSE 8080

CMD ["uvicorn", "backend.api.api_server:app", "--host", "0.0.0.0", "--port", "8080"]
