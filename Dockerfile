ARG PYTHON_IMAGE=python:3.14.3-slim-trixie@sha256:5e59aae31ff0e87511226be8e2b94d78c58f05216efda3b07dbbed938ec8583b

FROM ${PYTHON_IMAGE} AS build-stage

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      gcc \
      build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY . /app/

RUN pip install --upgrade pip && \
    pip install .

FROM ${PYTHON_IMAGE} AS prod-stage

COPY --from=build-stage /usr/local /usr/local

RUN mkdir -m 0755 /etc/contentbot

# Downloaded files are 0600 by default, the contentbot user has to read it.
ADD --checksum=sha256:39a4ead879cc8283de87f2ec58e7b4b340d6caa724db1b52a91dccf2f273c5e7 --chmod=0644 \
    https://github.com/dwyl/english-words/raw/20f5cc9b3f0ccc8ce45d814c532b7c2031bba31c/words.txt \
    /etc/contentbot/eng_dict.txt

# Runs as an unprivileged user, by UID so Kubernetes' runAsNonRoot can check it.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin contentbot
USER 10001

ENTRYPOINT ["contentbot"]
