### Builder stage: install dependencies and collect static files
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/
RUN python -m pip install --upgrade pip setuptools wheel && \
	pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN python manage.py collectstatic --noinput || true

### Runtime stage: smaller image, non-root user
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user for running the app
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
WORKDIR /app

# Copy only what we need from the builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://127.0.0.1:8000/ || exit 1

CMD ["gunicorn", "awareness_portal.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
