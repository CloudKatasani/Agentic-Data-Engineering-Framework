FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY adef ./adef
COPY web ./web
COPY skills ./skills
COPY agents ./agents
COPY adapters ./adapters
COPY demo-data ./demo-data
ENV ADEF_HOME=/data PYTHONUNBUFFERED=1
RUN useradd -m adef && mkdir -p /data && chown adef /data
USER adef
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "adef", "serve", "--host", "0.0.0.0", "--port", "8000"]
