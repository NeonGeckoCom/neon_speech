FROM python:3.10-slim AS base

LABEL vendor=neon.ai \
    ai.neon.name="neon-speech"

ENV OVOS_CONFIG_BASE_FOLDER=neon
ENV OVOS_CONFIG_FILENAME=neon.yaml
ENV XDG_CONFIG_HOME=/config

RUN apt-get update && \
  apt-get install -y \
    curl \
    jq \
    alsa-utils \
    libasound2-plugins \
    libpulse-dev \
    pulseaudio-utils \
    sox \
    swig \
    portaudio19-dev \
    flac \
    gcc \
    ffmpeg \
    wget \
    unzip \
    git

COPY . /neon_speech
WORKDIR /neon_speech

# cython included for Nemo package build
RUN pip install --no-cache-dir wheel cython && \
    pip install --no-cache-dir .[docker] --extra-index-url https://download.pytorch.org/whl/cpu

# Get vosk model for WW detection
RUN mkdir -p /root/.local/share/neon && \
    cd /root/.local/share/neon && \
    wget -q -O vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    unzip vosk-model-small-en-us-0.15.zip && \
    rm vosk-model-small-en-us-0.15.zip



COPY docker_overlay/ /
RUN chmod ugo+x /root/run.sh

RUN neon-speech install-dependencies

HEALTHCHECK CMD "/opt/neon/healthcheck.sh"
CMD ["/root/run.sh"]

FROM base AS default_model
RUN neon-speech init-plugin
