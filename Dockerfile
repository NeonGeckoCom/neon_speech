FROM python:3.8

ADD . /neon_speech
WORKDIR /neon_speech


RUN apt-get update && \
  apt-get install -y  \
    alsa-utils  \
    libasound2-plugins  \
    libpulse-dev  \
    pulseaudio-utils  \
    sox  \
    swig  \
    portaudio19-dev  \
    flac && \
  pip install \
    wheel \
    . \
    holmesv \
    git+https://github.com/neongeckocom/neon-stt-plugin-deepspeech_stream_local \
    git+https://github.com/neongeckocom/neon-stt-plugin-google_cloud_streaming \
    chatterbox-wake-word-plugin-dummy \
    ovos-ww-plugin-pocketsphinx \
    ovos-ww-plugin-precise

COPY docker_overlay/client.conf /etc/pulse/client.conf

RUN useradd -ms /bin/bash neon && \
    usermod -a -G audio neon
USER neon

COPY docker_overlay/asoundrc /home/neon/.asoundrc
COPY docker_overlay/mycroft.conf /home/neon/.mycroft/mycroft.conf

CMD ["neon_speech_client"]