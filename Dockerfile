FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends gcc pkg-config libmariadb-dev libmariadb3 netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 aza
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=aza:aza . .
RUN chmod +x deploy/entrypoint.sh
USER aza
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/').status==200 else 1)"
ENTRYPOINT ["deploy/entrypoint.sh"]
CMD ["gunicorn", "aza.wsgi:application", "-b", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--access-logfile", "-"]
