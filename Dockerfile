# Stage 1: build the React console
FROM node:20-alpine AS console
WORKDIR /console
COPY frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm ci --no-audit --no-fund && npm run build

# Stage 2: the Python API serving the built console at /
FROM python:3.11-slim
WORKDIR /app

# Optional extras, e.g. --build-arg EXTRAS="[multilingual]" for the
# multilingual embedder. Empty keeps the image small.
ARG EXTRAS=""

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY eval ./eval
RUN pip install --no-cache-dir -e ".${EXTRAS}"

COPY --from=console /console/dist ./frontend/dist

# Build the vector index for the bundled sample corpus at image build time
RUN rag ingest data/sample_docs

EXPOSE 8000
CMD ["rag", "serve", "--host", "0.0.0.0", "--port", "8000"]
