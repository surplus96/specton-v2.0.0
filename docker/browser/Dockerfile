FROM mcr.microsoft.com/playwright@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f
COPY docker/browser/package*.json /runner/
RUN cd /runner && npm ci --ignore-scripts --no-audit --no-fund
COPY specton/implementation/templates/frontend/package*.json /opt/ui/
RUN cd /opt/ui && npm ci --ignore-scripts --no-audit --no-fund
COPY specton/implementation/browser/*.mjs /runner/
USER 1000:1000
WORKDIR /workspace
CMD ["sleep","1200"]
