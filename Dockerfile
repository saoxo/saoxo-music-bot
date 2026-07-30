FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POT_PROVIDER_HOME=/root/bgutil-ytdlp-pot-provider/server

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN install -m 0755 "$(python -c 'import deno; print(deno.find_deno_bin())')" /usr/local/bin/deno \
    && git clone --depth 1 --branch 1.3.1 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        /root/bgutil-ytdlp-pot-provider \
    && cd /root/bgutil-ytdlp-pot-provider/server \
    && deno install --allow-scripts=npm:canvas --frozen

COPY bot.py config.py translations.py ./

EXPOSE 8000

CMD ["python", "bot.py"]
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY bot.py config.py translations.py ./

EXPOSE 8000

CMD ["python", "bot.py"]
