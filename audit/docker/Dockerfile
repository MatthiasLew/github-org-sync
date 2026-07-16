ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

# Install common utilities
RUN apt-get update && apt-get install -y \
    git \
    xvfb \
    libegl1 \
    libxkbcommon-x11-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libxcb-shape0 \
    libglib2.0-0 \
    libdbus-1-3 \
    libfontconfig1 \
    libxrender1 \
    libxi6 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

# Install python packages if they are not already present (for ubuntu/debian base images)
RUN if [ ! -f /usr/local/bin/python ] && [ ! -f /usr/bin/python3 ]; then \
        apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY . .

# Run installation and testing.
# Detect python command
RUN PYCMD="python3"; \
    if command -v python >/dev/null 2>&1; then \
        PYCMD="python"; \
    fi; \
    $PYCMD -m venv .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -e ".[dev]"

CMD [ "sh", "-c", " \
    PYCMD='.venv/bin/python'; \
    $PYCMD -m ruff check . && \
    $PYCMD -m ruff format --check . && \
    $PYCMD -m mypy src && \
    QT_DEBUG_PLUGINS=1 xvfb-run -a $PYCMD -m pytest -q \
" ]
