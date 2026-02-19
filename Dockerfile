ARG PYTHON_IMAGE=python:3.14.3-slim-trixie

FROM ${PYTHON_IMAGE} AS build-stage

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      gcc \
      build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml

RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -e .

COPY ./src/cytubebot/ /app/cytubebot/

FROM ${PYTHON_IMAGE} AS prod-stage

COPY --from=build-stage /app/venv/ /app/venv/
COPY --from=build-stage /app/cytubebot/ /app/cytubebot/

ADD https://github.com/dwyl/english-words/raw/master/words.txt /app/cytubebot/randomvideo/eng_dict.txt

ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

ENTRYPOINT ["contentbot"]
