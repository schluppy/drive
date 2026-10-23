FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/tmp XDG_CACHE_HOME=/tmp/.cache
WORKDIR /app
# msmtp für den Mailversand
RUN apt-get update && apt-get install -y --no-install-recommends \
      msmtp ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build DJANGO_DEBUG=0 python manage.py collectstatic --noinput \
    && mkdir -p /app/media \
    && chown 1000:1000 /app/media
# Laufzeit ohne root: UID/GID 1000. Programmdateien gehören root und sind nur lesbar,
# schreiben darf der Prozess nur in /app/media (Volume: Fahrzeugfotos, Import) und /tmp.
USER 1000:1000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi -b 0.0.0.0:8000 -w 3 --timeout 120"]
