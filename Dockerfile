# NetSentinel - single image, runs either role via NETSENTINEL_ROLE.
# Multi-arch: builds for linux/amd64 and linux/arm64 (Raspberry Pi 4).
FROM python:3.12-slim AS base

# nmap for discovery/port scans; libpcap for scapy passive DNS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nmap libpcap0.8 iproute2 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NETSENTINEL_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
RUN pip install --no-cache-dir ".[sensor]"

RUN useradd --system --uid 10001 sentinel && mkdir -p /data && chown sentinel /data
USER sentinel
VOLUME ["/data"]
EXPOSE 8080

# Default to the hub; compose overrides command for the sensor.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8080/healthz || exit 1
CMD ["netsentinel", "hub"]
