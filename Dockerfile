FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY adpe ./adpe
COPY web ./web
COPY skills ./skills
COPY agents ./agents
COPY adapters ./adapters
ENV ADPE_HOME=/data PYTHONUNBUFFERED=1
RUN useradd -m adpe && mkdir -p /data && chown adpe /data
USER adpe
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "adpe", "serve", "--host", "0.0.0.0", "--port", "8000"]
