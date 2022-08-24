# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from mycroft.audio import is_speaking
from mycroft.client.speech.mic import get_silence, ResponsiveRecognizer
from neon_utils import LOG
from speech_recognition import AudioSource, AudioData

from neon_transformers.audio_transformers import AudioTransformersService


class NeonResponsiveRecognizer(ResponsiveRecognizer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_speech = False
        self.audio_consumers = AudioTransformersService(self.loop.bus,
                                                        config=self.config)

    @property
    def use_wake_word(self):
        """
        Property to query configuration for wake word state
        """
        return self.config["listener"].get('wake_word_enabled', True)

    @use_wake_word.setter
    def use_wake_word(self, new_val: bool):
        if not isinstance(new_val, bool):
            raise ValueError(f"Expected bool, got: {new_val}")
        self.config["listener"]["wake_word_enabled"] = new_val
        # TODO: Write config changes to disk?

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def record_sound_chunk(self, source):
        chunk = super().record_sound_chunk(source)
        if self.in_speech:
            audio_data = self._create_audio_data(chunk, source)
            self.audio_consumers.feed_speech(audio_data)
        return chunk

    def _record_phrase(self, *args, **kwargs):
        self.in_speech = True
        byte_data = super()._record_phrase(*args, **kwargs)
        self.in_speech = False
        return byte_data

    def _skip_wake_word(self):
        """
        Check if told programmatically to skip the wake word.
        For example when we are in a dialog with the user.
        """
        if not self.use_wake_word:
            return True
        elif self._listen_triggered:
            self._listen_triggered = False
            return True
        return False

    def check_for_hotwords(self, audio_data):
        found = False
        for ww in super().check_for_hotwords(audio_data):
            found = True
            yield ww
        if not found:
            self.audio_consumers.feed_audio(audio_data)

    def listen(self, source, stream):
        """Listens for chunks of audio that Mycroft should perform STT on.

        This will listen continuously for a wake-up-word, then return the
        audio chunk containing the spoken phrase that comes immediately
        afterwards.

        Args:
            source (AudioSource):  Source producing the audio chunks
            stream (AudioStreamHandler): Stream target that will receive chunks
                                         of the utterance audio while it is
                                         being recorded

        Returns:
            (AudioData, lang): audio with the user's utterance (minus the
                               wake-up-word), stt_lang
        """
        assert isinstance(source, AudioSource), "Source must be an AudioSource"

        # If skipping wake words, just pass audio to our streaming STT
        if self.loop.stt.can_stream and not self.use_wake_word:
            LOG.debug("skipping wake words")
            lang = self.loop.stt.lang
            self.loop.emit("recognizer_loop:record_begin")
            self.loop.stt.stream.stream_start()
            frame_data = get_silence(source.SAMPLE_WIDTH)
            LOG.debug("Stream starting!")
            # event set in OPM
            while not self.loop.stt.transcript_ready.is_set():
                # Pass audio until STT tells us to stop
                # (this is called again immediately)
                chunk = self.record_sound_chunk(source)
                if not is_speaking():
                    # Filter out Neon speech
                    self.loop.stt.stream.stream_chunk(chunk)
                    frame_data += chunk
            LOG.debug("stream ended!")
            audio_data = self._create_audio_data(frame_data, source)
            self.loop.emit("recognizer_loop:record_end")
        # If using wake words, wait until the wake_word is detected and
        # then record the following phrase
        else:
            audio_data, lang = super().listen(source, stream)
        # one of the default plugins saves the speech to file and
        # adds "filename" to context
        audio_data, context = self.audio_consumers.transform(audio_data)
        context["lang"] = lang
        return audio_data, context
