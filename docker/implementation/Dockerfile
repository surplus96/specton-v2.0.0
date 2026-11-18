ARG PYTHON_IMAGE=python@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY specton/implementation/templates/runtime/requirements.txt /runner/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /runner/requirements.txt
COPY specton/implementation/templates/runtime/probe.py.txt /runner/probe.py
COPY specton/implementation/templates/runtime/acceptance_runner.py.txt /runner/acceptance_runner.py
USER 1000:1000
WORKDIR /workspace
CMD ["sleep", "300"]
