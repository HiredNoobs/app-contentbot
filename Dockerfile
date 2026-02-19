ARG PYTHON_IMAGE=python:3.14.3-slim-trixie

FROM ${PYTHON_IMAGE} AS build-stage

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      gcc \
      build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY . /app/contentbot

RUN python -m venv /app/contentbot/venv && \
    /app/contentbot/venv/bin/pip install --upgrade pip && \
    /app/contentbot/venv/bin/pip install -e .

FROM ${PYTHON_IMAGE} AS prod-stage

COPY --from=build-stage /app/contentbot/ /app/contentbot/

ADD https://github.com/dwyl/english-words/raw/master/words.txt /app/contentbot/randomvideo/eng_dict.txt

ENV PATH="/app/contentbot/venv/bin:$PATH"

WORKDIR /app

ENTRYPOINT ["contentbot"]
