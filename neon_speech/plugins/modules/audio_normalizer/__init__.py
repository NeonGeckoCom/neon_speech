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
from pydub import AudioSegment
import tempfile
from os.path import join
import time
from speech_recognition import AudioData


class AudioNormalizer(AudioParser):
    def __init__(self, config=None):
        super().__init__("audio_normalizer", 1, config=config)
        # silence_threshold in dB
        self.thresh = self.config.get("threshold", 10)
        # final volume  in dB
        self.final_db = self.config.get("final_volume", -18.0)

    def trim_silence(self, audio_data):
        if isinstance(audio_data, AudioData):
            audio_data = AudioSegment(
                data=audio_data.frame_data,
                sample_width=audio_data.sample_width,
                frame_rate=audio_data.sample_rate,
                channels=1

            )
        assert isinstance(audio_data, AudioSegment)
        start_trim = self.detect_leading_silence(audio_data,
                                                 audio_data.dBFS + self.thresh)
        end_trim = self.detect_leading_silence(audio_data.reverse(),
                                               audio_data.dBFS + self.thresh
                                               // 3)
        trimmed = audio_data[start_trim:-end_trim]
        # if len(trimmed) >= 0.15 * len(audio_data):
        audio_data = trimmed
        if audio_data.dBFS != self.final_db:
            change_needed = self.final_db - audio_data.dBFS
            audio_data = audio_data.apply_gain(change_needed)

        filename = join(tempfile.gettempdir(), str(time.time()) + ".wav")
        audio_data.export(filename, format="wav")
        with open(filename, "rb") as byte_data:
            new_audio_data = AudioData(byte_data.read(),
                                       audio_data.frame_rate,
                                       audio_data.sample_width)
            return new_audio_data, filename

    @staticmethod
    def detect_leading_silence(sound, silence_threshold=-36.0, chunk_size=10):
        """
        sound is a pydub.AudioSegment
        silence_threshold in dB
        chunk_size in ms
        iterate over chunks until you find the first one with sound
        """
        trim_ms = 0  # ms
        assert chunk_size > 0  # to avoid infinite loop
        while sound[trim_ms:trim_ms + chunk_size].dBFS < silence_threshold \
                and trim_ms < len(sound):
            trim_ms += chunk_size
        return trim_ms

    def on_speech_end(self, audio_data):
        audio_data, filename = self.trim_silence(audio_data)
        return audio_data, {"audio_filename": filename}


def create_module(config=None):
    return AudioNormalizer(config=config)
