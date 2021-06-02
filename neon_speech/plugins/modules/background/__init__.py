# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2021 Neongecko.com Inc.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions
#    and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions
#    and the following disclaimer in the documentation and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
# USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from neon_speech.plugins import AudioParser
import audioop
from math import log10


class BackgroundNoise(AudioParser):
    def __init__(self, config=None):
        super().__init__("background_noise", 10, config)
        self._audio = None
        self._prediction = None
        self._buffer_size = 5  # seconds

    @staticmethod
    def seconds_to_size(seconds):
        # 1 seconds of audio.frame_data = 44032
        return int(seconds * 44032)

    def on_audio(self, audio_data):
        max_size = self.seconds_to_size(self._buffer_size)
        if self._audio:
            self._audio.frame_data += audio_data.frame_data
        else:
            self._audio = audio_data
        if len(self._audio.frame_data) > max_size:
            self._audio.frame_data = self._audio.frame_data[-max_size:]

    def noise_level(self):
        # NOTE: on_audio will usually include a partial wake word at the end,
        # discard the last ~0.7 seconds of audio
        audio = self._audio.frame_data[:-self.seconds_to_size(0.7)]
        rms = audioop.rms(audio, 2)
        decibel = 20 * log10(rms)
        return decibel

    def on_hotword(self, audio_data):
        # In here we can run predictions, for example classify the
        # background noise, or save the audio and if STT fails we can
        # then perform STT to enable things like "tell me a joke, Neon"
        self._prediction = self.noise_level()

        self._audio = None

    def on_speech_end(self, audio_data):
        return audio_data, {"noise_level": self._prediction}


def create_module(config=None):
    return BackgroundNoise(config=config)

