#!/usr/bin/env sh
# Container entrypoint: bring the DB schema up to date, then hand off to the container command.
#
# `set -e`        — if the migration fails, abort boot. Never serve on a half-migrated schema.
# `alembic ...`   — idempotent: no pending migrations = instant no-op (safe on every restart/wake).
# `exec "$@"`     — replace this shell with the CMD (uvicorn), so the server is PID 1 and receives
#                   SIGTERM for clean shutdowns. This is the standard Docker entrypoint idiom.
#
# ponytail: migrate-on-boot assumes a single instance (true on Render free tier). If this ever scales
# to multiple instances, move `alembic upgrade head` to a dedicated release/pre-deploy step so two
# replicas don't race the migration.
set -e
alembic upgrade head
exec "$@"
