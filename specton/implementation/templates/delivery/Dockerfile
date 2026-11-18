ARG UI_IMAGE=mcr.microsoft.com/playwright@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f
ARG PYTHON_IMAGE=python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
FROM ${UI_IMAGE} AS ui
USER root
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt /runner/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /runner/requirements.txt
ENV APP_AUTH_MODE=session
WORKDIR /app/backend
COPY backend/ /app/backend/
COPY LICENSE /app/LICENSE
COPY --from=ui /build/dist/ /app/frontend/dist/
COPY --from=ui /build/node_modules/react/LICENSE /app/licenses/react.txt
COPY --from=ui /build/node_modules/react-dom/LICENSE /app/licenses/react-dom.txt
COPY --from=ui /build/node_modules/scheduler/LICENSE /app/licenses/scheduler.txt
USER 1000:1000
EXPOSE 8080
CMD ["uvicorn","serve:app","--host","0.0.0.0","--port","8080","--no-access-log"]
