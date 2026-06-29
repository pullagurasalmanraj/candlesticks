FROM postgres:16-alpine

COPY backend/schema.sql /docker-entrypoint-initdb.d/01-schema.sql
