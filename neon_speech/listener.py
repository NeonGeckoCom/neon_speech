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
from queue import Queue
from mycroft.configuration import Configuration
from mycroft.client.speech.listener import RecognizerLoop, AudioConsumer, AudioProducer, recognizer_conf_hash, \
    find_input_device, RecognizerLoopState
from mycroft.client.speech.mic import MutableMicrophone
from mycroft.util.log import LOG
from mycroft.metrics import Stopwatch

from neon_speech.mic import NeonResponsiveRecognizer
from neon_speech.stt import STTFactory


class NeonAudioConsumer(AudioConsumer):
    def process(self, audio, context=None):
        # NOTE: in the parent class context is a string for lang
        # in neon we pass a dict around instead
        lang = context.get("lang") or self.loop.stt.lang

        if audio is None:
            return

        if self._audio_length(audio) < self.MIN_AUDIO_SIZE:
            LOG.warning("Audio too short to be processed")
        else:
            stopwatch = Stopwatch()
            with stopwatch:
                transcription = self.transcribe(audio, lang)
            if transcription:
                ident = str(stopwatch.timestamp) + str(hash(transcription))
                if isinstance(transcription, str):
                    transcription = [transcription]
                # STT succeeded, send the transcribed speech on for processing
                payload = {
                    'utterances': transcription,
                    'lang': lang,
                    'ident': ident,
                    'context': context
                }
                self.loop.emit("recognizer_loop:utterance", payload)


class NeonRecognizerLoop(RecognizerLoop):
    """ EventEmitter loop running speech recognition.

    Local wake word recognizer and remote general speech recognition.
    """
    def __init__(self, bus, watchdog=None, stt=None, fallback_stt=None,
                 config=None):
        self.config = config
        super().__init__(bus, watchdog, stt, fallback_stt)

    # def bind_transformers(self, parsers_service):
    #     self.responsive_recognizer.bind(parsers_service)

    def _load_config(self):
        """Load configuration parameters from configuration."""
        config = Configuration.get()
        self.config_core = config
        self._config_hash = recognizer_conf_hash(config)
        self.lang = config.get('lang')
        self.config = config.get('listener')
        rate = self.config.get('sample_rate')

        device_index = self.config.get('device_index')
        device_name = self.config.get('device_name')
        if not device_index and device_name:
            device_index = find_input_device(device_name)

        LOG.debug('Using microphone (None = default): ' + str(device_index))

        self.microphone = MutableMicrophone(device_index, rate,
                                            mute=self.mute_calls > 0)
        self.create_hotword_engines()
        self.state = RecognizerLoopState()
        self.responsive_recognizer = NeonResponsiveRecognizer(self)

    def start_async(self):
        """Start consumer and producer threads."""
        self.state.running = True
        if not self.stt:
            self.stt = STTFactory.create(self.config)
        self.queue = Queue()
        self.audio_consumer = NeonAudioConsumer(self)
        self.audio_consumer.start()
        self.audio_producer = AudioProducer(self)
        self.audio_producer.start()
