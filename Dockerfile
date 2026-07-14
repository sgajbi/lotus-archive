FROM python:3.12-slim AS wheel-builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ARG SERVICE_VERSION=0.1.0
ARG GIT_COMMIT_SHA=local
ARG GIT_REPOSITORY_URL=https://github.com/sgajbi/lotus-archive
ARG GIT_REF=local
ARG BUILD_TIMESTAMP_UTC=local
ARG CI_RUN_ID=local
ARG IMAGE_DIGEST=not-published

LABEL org.opencontainers.image.title="lotus-archive" \
      org.opencontainers.image.description="Lotus generated-document archive service" \
      org.opencontainers.image.version="${SERVICE_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT_SHA}" \
      org.opencontainers.image.source="${GIT_REPOSITORY_URL}" \
      org.opencontainers.image.ref.name="${GIT_REF}" \
      org.opencontainers.image.created="${BUILD_TIMESTAMP_UTC}" \
      com.lotus.ci.run-id="${CI_RUN_ID}"

ENV LOTUS_SERVICE_NAME=lotus-archive \
    LOTUS_SERVICE_VERSION="${SERVICE_VERSION}" \
    LOTUS_BUILD_COMMIT_SHA="${GIT_COMMIT_SHA}" \
    LOTUS_BUILD_REPOSITORY_URL="${GIT_REPOSITORY_URL}" \
    LOTUS_BUILD_GIT_REF="${GIT_REF}" \
    LOTUS_BUILD_TIMESTAMP_UTC="${BUILD_TIMESTAMP_UTC}" \
    LOTUS_BUILD_CI_RUN_ID="${CI_RUN_ID}" \
    LOTUS_BUILD_IMAGE_DIGEST="${IMAGE_DIGEST}"

WORKDIR /app
COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels \
    && useradd --create-home --shell /usr/sbin/nologin lotus

USER lotus
EXPOSE 8150
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8150"]
