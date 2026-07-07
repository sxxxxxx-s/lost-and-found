FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

FROM base AS web-agent
COPY *.py ./
COPY flows/ ./flows/
COPY web/ ./web/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["python", "-B", "web_server.py"]

FROM base AS item-service
COPY data.py ./data.py
COPY services/item_service.py ./services/item_service.py
USER 10001:10001
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2)"]
CMD ["python", "-B", "services/item_service.py"]

FROM base AS claim-service
COPY data.py ./data.py
COPY services/claim_service.py ./services/claim_service.py
USER 10001:10001
EXPOSE 8002
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/healthz', timeout=2)"]
CMD ["python", "-B", "services/claim_service.py"]

FROM base AS handover-service
COPY data.py ./data.py
COPY services/handover_service.py ./services/handover_service.py
USER 10001:10001
EXPOSE 8003
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/healthz', timeout=2)"]
CMD ["python", "-B", "services/handover_service.py"]
