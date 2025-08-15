ARG PYTHON_IMAGE=python:3.11-slim-bullseye

#################################################
# Create virtualenv and install dependencies
#################################################
FROM ${PYTHON_IMAGE} AS build-stage

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      gcc \
      build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -e .

COPY ./cytubebot/ /app/cytubebot/

#################################################
# Build deployable container
#################################################
FROM ${PYTHON_IMAGE} AS prod-stage

COPY --from=build-stage /app/venv/ /app/venv/
COPY --from=build-stage /app/cytubebot/ /app/cytubebot/

ADD https://github.com/dwyl/english-words/raw/master/words.txt /app/cytubebot/randomvideo/eng_dict.txt

ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

CMD ["python", "-m", "cytubebot"]
