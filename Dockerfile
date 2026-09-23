ARG PYTHON_IMAGE=python:3.14.3-slim-trixie

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

ADD https://github.com/dwyl/english-words/raw/20f5cc9b3f0ccc8ce45d814c532b7c2031bba31c/words.txt \
    /etc/contentbot/eng_dict.txt

ENTRYPOINT ["contentbot"]
