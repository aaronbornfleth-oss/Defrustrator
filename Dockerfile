FROM node:22-bookworm AS ui
WORKDIR /src/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY samples /app/samples
COPY scripts/start.sh /app/start.sh
COPY --from=ui /src/frontend/dist /app/frontend/dist
RUN chmod +x /app/start.sh
EXPOSE 8000
CMD ["/app/start.sh"]
