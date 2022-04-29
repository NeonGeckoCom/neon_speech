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
    ffmpeg \
    git

ADD . /neon_speech
WORKDIR /neon_speech

RUN pip install wheel && \
  pip install .[docker]

COPY docker_overlay/ /
RUN chmod ugo+x /root/run.sh

CMD ["/root/run.sh"]