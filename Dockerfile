FROM python:3.12-slim
ARG WITH_DB2=false
# git: the Build agent commits generated pipeline code to a run-local repository
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-db2.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_DB2" = "true" ]; then pip install --no-cache-dir -r requirements-db2.txt; fi
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
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1
# Binding to 0.0.0.0 inside the container requires ADEF_API_TOKEN (the server refuses otherwise).
CMD ["python", "-m", "adef", "serve", "--host", "0.0.0.0", "--port", "8000"]
