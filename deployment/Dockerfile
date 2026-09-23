FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends fonts-arphic-uming && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY cases ./cases
COPY fixtures/demo/reference_5zone ./fixtures/demo/reference_5zone
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --uid 10001 --create-home vra && mkdir runtime && chown vra:vra runtime
USER vra
ENV DEMO_MODE=false VRA_DATA_DIR=/app/runtime ENERGYPLUS_EXE=/opt/energyplus/energyplus
EXPOSE 8766
CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8766", "--workers", "1"]
