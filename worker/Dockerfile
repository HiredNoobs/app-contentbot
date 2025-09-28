ARG PYTHON_IMAGE=python:3.13-slim-trixie

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

COPY pyproject.toml /app/pyproject.toml

RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -e .

COPY ./src/worker/ /app/worker/

#################################################
# Build deployable container
#################################################
FROM ${PYTHON_IMAGE} AS prod-stage

COPY --from=build-stage /app/venv/ /app/venv/
COPY --from=build-stage /app/worker/ /app/worker/

ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

CMD ["python", "-m", "worker"]
