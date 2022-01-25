FROM python:3.8-slim

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
    ffmpeg

ADD . /neon_speech
WORKDIR /neon_speech

RUN pip install wheel && \
  pip install .[docker]

COPY docker_overlay/asoundrc /root/.asoundrc
COPY docker_overlay/client.conf /etc/pulse/client.conf

CMD ["neon_speech_client"]