# News Desk backend — container image for Cloud Run / Render / Fly.io.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NEWS_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY news_agents.py ./

# Cloud Run / Render inject $PORT; the app reads it (PORT > NEWS_PORT > 8181) and binds NEWS_HOST.
EXPOSE 8080
CMD ["python", "news_agents.py"]
