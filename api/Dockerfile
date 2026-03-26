FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG INSTALL_DEV=false

COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then python -m pip install --no-cache-dir -r requirements-dev.txt; fi \
    && pip cache purge

# Add non-root user
RUN useradd -u 10001 -m appuser

# Alembic config and application code
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Adjust permissions
RUN chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

COPY ./app/healthcheck.py /app/app/healthcheck.py

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 CMD ["python", "/app/app/healthcheck.py"]

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
