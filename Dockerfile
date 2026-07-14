FROM python:3.12-slim AS wheel-builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ARG LOTUS_ARCHIVE_VERSION=0.1.0
ARG LOTUS_ARCHIVE_COMMIT_SHA=local
ARG LOTUS_ARCHIVE_REPOSITORY_URL=https://github.com/sgajbi/lotus-archive
ARG LOTUS_ARCHIVE_BUILD_REF=local
ARG LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC=local
ARG LOTUS_ARCHIVE_CI_RUN_ID=local
ARG LOTUS_ARCHIVE_IMAGE_REF=lotus-archive:local
ARG LOTUS_ARCHIVE_IMAGE_DIGEST=not-published

LABEL org.opencontainers.image.title="lotus-archive" \
      org.opencontainers.image.description="Lotus generated-document archive service" \
      org.opencontainers.image.version="${LOTUS_ARCHIVE_VERSION}" \
      org.opencontainers.image.revision="${LOTUS_ARCHIVE_COMMIT_SHA}" \
      org.opencontainers.image.source="${LOTUS_ARCHIVE_REPOSITORY_URL}" \
      org.opencontainers.image.ref.name="${LOTUS_ARCHIVE_BUILD_REF}" \
      org.opencontainers.image.created="${LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC}" \
      io.lotus.pipeline.run-id="${LOTUS_ARCHIVE_CI_RUN_ID}" \
      io.lotus.image.ref="${LOTUS_ARCHIVE_IMAGE_REF}" \
      io.lotus.image.digest="${LOTUS_ARCHIVE_IMAGE_DIGEST}"

ENV LOTUS_ARCHIVE_SERVICE_NAME=lotus-archive \
    LOTUS_ARCHIVE_VERSION="${LOTUS_ARCHIVE_VERSION}" \
    LOTUS_ARCHIVE_COMMIT_SHA="${LOTUS_ARCHIVE_COMMIT_SHA}" \
    LOTUS_ARCHIVE_REPOSITORY_URL="${LOTUS_ARCHIVE_REPOSITORY_URL}" \
    LOTUS_ARCHIVE_BUILD_REF="${LOTUS_ARCHIVE_BUILD_REF}" \
    LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC="${LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC}" \
    LOTUS_ARCHIVE_CI_RUN_ID="${LOTUS_ARCHIVE_CI_RUN_ID}" \
    LOTUS_ARCHIVE_IMAGE_REF="${LOTUS_ARCHIVE_IMAGE_REF}" \
    LOTUS_ARCHIVE_IMAGE_DIGEST="${LOTUS_ARCHIVE_IMAGE_DIGEST}" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels \
    && useradd --create-home --shell /usr/sbin/nologin lotus

USER lotus
EXPOSE 8150
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8150"]
