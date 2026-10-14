FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite database lives on a volume mounted at /data (see docker-compose.yaml).
RUN mkdir -p /data

EXPOSE 8003

# Bring the database schema up to date before starting, so a rebuild after `git pull` applies new migrations.
# If a migration fails the container exits instead of serving requests against a stale schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8003"]
