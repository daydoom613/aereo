# The geospatial wheels (pyogrio, shapely, pyproj) bundle GDAL, GEOS and PROJ, so the slim
# image needs no system packages.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATABASE_URL=sqlite:////data/measurements.db

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .

# Run as an unprivileged user that owns only the data directory.
RUN useradd --system --no-create-home appuser \
    && mkdir /data \
    && chown appuser /data
USER appuser
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
