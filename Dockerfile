FROM python:3.12-slim AS wheel-builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

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

# CVE-2026-14456 (HIGH): the python:3.12-slim base ships openssl 3.5.6-1~deb13u2 and Debian has
# published 3.5.7-1~deb13u2. Upgraded here rather than waiting for the upstream image, because the
# release and pull-request vulnerability gates both fail on it - see issue #85.
#
# Targeted, not a blanket `apt-get upgrade`: a distribution-wide upgrade in an image build changes
# far more than the finding requires and makes the diff unreviewable. Remove this block once the
# base image carries 3.5.7 or later; `tests/unit/test_openssl_runtime_upgrade.py` records how to
# check, so it does not linger after it stops being needed.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        openssl libssl3t64 openssl-provider-legacy \
    && dpkg --compare-versions "$(dpkg-query --show --showformat='${Version}' openssl)" ge \
        "3.5.7-1~deb13u2" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=wheel-builder /wheels/lotus_archive-*.whl /wheels/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --only-binary=:all: /wheels/lotus_archive-*.whl \
    && python -m pip uninstall --yes pip \
    && rm -rf /wheels \
    && useradd --create-home --shell /usr/sbin/nologin lotus

USER lotus
EXPOSE 8150
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8150"]
