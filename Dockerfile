# syntax=docker/dockerfile:experimental
FROM python:3.11.8 as builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/app"

ARG POETRY_VERSION=1.8.3
RUN pip install poetry==$POETRY_VERSION

COPY poetry.lock  .
COPY pyproject.toml .

# Project initialization:
RUN poetry config virtualenvs.in-project true && poetry install --no-interaction --no-ansi --no-dev

FROM builder AS final

ENV DEBUG=0
ENV DEV=0
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="$PYTHONPATH:/app/.venv/bin/python3"

COPY . .

CMD ["sh", "-c", "python manage.py deploy all example && tail -f /dev/null"]
