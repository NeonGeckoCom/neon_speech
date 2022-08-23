FROM python:3.8-slim as base

LABEL vendor=neon.ai \
    ai.neon.name="neon-speech"

ENV NEON_CONFIG_PATH /config

RUN apt-get update && \
  apt-get install -y \
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

ADD . /neon_speech
WORKDIR /neon_speech

RUN pip install wheel && \
  pip install .[docker]

# Get vosk model for WW detection
RUN mkdir -p /root/.local/share/neon && \
    cd /root/.local/share/neon && \
    wget -O vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    unzip vosk-model-small-en-us-0.15.zip && \
    rm vosk-model-small-en-us-0.15.zip



COPY docker_overlay/ /
RUN chmod ugo+x /root/run.sh

RUN neon-speech install-plugin -f

CMD ["/root/run.sh"]

FROM base as default_model
RUN neon-speech init-plugin