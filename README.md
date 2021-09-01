# Neon Speech
Speech (Voice) Module for Neon Core. This module can be treated as a replacement for the
[mycroft-core](https://github.com/MycroftAI/mycroft-core) speech module. This module handles input audio, performs STT, 
and optionally returns the text or forwards it to the skills module for intent parsing.

## Neon Enhancements
`neon-speech` extends `mycroft-speech` with the following added functionality:
* Support for continuous STT without a wake word
* Audio processing module plugin system to modify audio and extract context
* Messagebus API listeners to handle outside requests for STT or inputs to the skills module
* Arbitrary configuration supported by passing at module init


## Compatibility
Mycroft STT and Wake Word plugins are compatible with `neon-speech`, with the exception of skipping wake words,
which is currently only supported by Neon STT plugins.

## Running in Docker
The included `Dockerfile` may be used to build a docker container for the neon_audio module. The below command may be used
to start the container.

```
docker run -d \
--network=host \
-v ~/.local/share/neon:/home/neon/.local/share/neon:rw \
-v ~/.config/neon:/home/neon/.config/neon:rw \
-v ~/.config/pulse/cookie:/home/mycroft/.config/pulse/cookie:ro \ 
-v ${XDG_RUNTIME_DIR}/pulse:${XDG_RUNTIME_DIR}/pulse:ro \
-v /tmp:/tmp:rw \
--device=/dev/snd:/dev/snd \
-e PULSE_SERVER=unix:${XDG_RUNTIME_DIR}/pulse/native \
-e PULSE_COOKIE=/home/neon/.config/pulse/cookie \
neon_speech
```
