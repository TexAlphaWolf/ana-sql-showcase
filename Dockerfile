FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
    && useradd --system --no-create-home --uid 10001 sqlshow \
    && install -d -o sqlshow /out

# sqlshow only talks to the database named by SQLSHOW_DSN and writes its report to /out. It needs no privilege:
# run it with --read-only, --cap-drop ALL and --tmpfs /tmp (matplotlib's cache).
USER sqlshow
WORKDIR /out
ENTRYPOINT ["sqlshow"]
CMD ["--help"]
