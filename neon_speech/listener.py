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

from queue import Queue
from threading import Event
from typing import List

# from neon_utils.configuration_utils import get_neon_device_type
from ovos_utils.log import LOG
from ovos_utils.metrics import Stopwatch
from ovos_config.config import Configuration
from mycroft.client.speech.listener import RecognizerLoop, AudioConsumer, \
    AudioProducer, recognizer_conf_hash, \
    find_input_device, RecognizerLoopState
from mycroft.client.speech.mic import MutableMicrophone

from neon_speech.mic import NeonResponsiveRecognizer
from neon_speech.stt import STTFactory


class NeonAudioConsumer(AudioConsumer):
    def process(self, audio, context=None):
        context = context or {}
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
            if any(transcription):
                ident = str(stopwatch.timestamp) + str(hash(transcription[0]))
                # STT succeeded, send the transcribed speech on for processing
                payload = {
                    'utterances': transcription,
                    'lang': lang,
                    'ident': ident,
                    'context': context
                }
                self.loop.emit("recognizer_loop:utterance", payload)
            else:
                LOG.debug(f"Nothing transcribed")

    def transcribe(self, audio, lang) -> List[str]:
        def send_unknown_intent():
            """ Send message that nothing was transcribed. """
            self.loop.emit('recognizer_loop:speech.recognition.unknown')

        try:
            # Invoke the STT engine on the audio clip
            try:
                transcriptions = self.loop.stt.execute(audio, language=lang)
                LOG.debug(f'transcriptions={transcriptions}')
                if not transcriptions or (isinstance(transcriptions, list)
                                          and not any(transcriptions)):
                    raise RuntimeError("Primary STT returned nothing")
            except Exception as e:
                self.loop.init_fallback_stt()
                if self.loop.fallback_stt:
                    LOG.warning(f"Using fallback STT, main plugin failed: {e}")
                    transcriptions = \
                        self.loop.fallback_stt.execute(audio, language=lang)
                else:
                    LOG.debug("No fallback_stt to try")
                    raise e
            if isinstance(transcriptions, str):
                LOG.info("Casting str transcriptions to list")
                transcriptions = [transcriptions]
            if transcriptions:
                transcriptions = [t.lower().strip() for t in transcriptions]
                LOG.debug(f"STT: {transcriptions}")
                if not any(transcriptions):
                    send_unknown_intent()
            else:
                send_unknown_intent()
                LOG.info('no words were transcribed')
            return transcriptions
        except Exception as e:
            send_unknown_intent()
            LOG.error(e)
            LOG.exception("Speech Recognition could not understand audio")
            return None


class NeonRecognizerLoop(RecognizerLoop):
    """ EventEmitter loop running speech recognition.

    Local wake word recognizer and remote general speech recognition.
    """
    def __init__(self, bus, watchdog=None, stt=None, fallback_stt=None):
        self.config_loaded = Event()
        self.microphone = None
        super().__init__(bus, watchdog, stt, fallback_stt)

    def _load_config(self):
        """
        Load configuration parameters from configuration and initialize
        self.microphone, self.responsive_recognizer
        """
        # self.config_core = self._init_config_core or Configuration.get()
        self.config_core = Configuration()
        self.config = self.config_core.get('listener')
        self._config_hash = recognizer_conf_hash(self.config_core)
        self.lang = self.config_core.get('lang')
        rate = self.config.get('sample_rate')

        device_index = self.config.get('device_index') or \
            self.config.get("dev_index")
        device_name = self.config.get('device_name')
        retry_mic = self.config.get('retry_mic_init', True)

        if not device_index and device_name:
            device_index = find_input_device(device_name)

        LOG.debug('Using microphone (None = default): ' + str(device_index))

        if self.microphone:
            try:
                assert self.microphone.stream is None
            except AssertionError:
                LOG.error("Microphone still active!!")
            LOG.info(f"Deleting old MutableMicrophone Instance")
            del self.microphone
        self.microphone = MutableMicrophone(device_index, rate,
                                            mute=self.mute_calls > 0,
                                            retry=retry_mic)
        if self.engines:
            for e in self.engines.values():
                try:
                    LOG.info(f"Deleting engine before reinitializing: {e}")
                    e.get('engine').stop()
                    del e['engine']
                except Exception as e:
                    LOG.exception(e)
        self.create_hotword_engines()
        self.state = RecognizerLoopState()
        self.responsive_recognizer = NeonResponsiveRecognizer(self)
        self.config_loaded.set()
        # TODO: Update recognizer to support passed config

    def init_fallback_stt(self):
        if not self.fallback_stt:
            clazz = self.get_fallback_stt()
            if clazz:
                LOG.debug(f"Initializing fallback STT engine")
                self.fallback_stt = clazz()

    def start_async(self):
        """Start consumer and producer threads."""
        self.state.running = True
        if not self.stt:
            self.stt = STTFactory.create(self.config_core)
        self.queue = Queue()
        self.audio_consumer = NeonAudioConsumer(self)
        self.audio_consumer.name = "audio_consumer"
        self.audio_consumer.start()
        self.audio_producer = AudioProducer(self)
        self.audio_producer.name = "audio_producer"
        try:
            # TODO: Patching bug in ovos-core
            self.microphone._start()
            self.microphone._stop()
            LOG.info("Microphone valid")
            self.audio_producer.start()
        except Exception as e:
            LOG.exception(e)
            LOG.error("Skipping audio_producer init")

    def stop(self):
        self.state.running = False
        if self.audio_producer:
            self.audio_producer.stop()

        # stop wake word detectors
        engines = list(self.engines.keys())
        for hotword in engines:
            try:
                self.engines[hotword]["engine"].stop()
                LOG.debug(f"stopped {hotword}")
                config = self.engines.pop(hotword)
                if config.get('engine'):
                    del config['engine']  # Make sure engine is removed
            except:
                LOG.exception(f"Failed to stop hotword engine: {hotword}")

        # wait for threads to shutdown
        try:
            if self.audio_producer and self.audio_producer.is_alive():
                self.audio_producer.join(1)
                if self.audio_producer.is_alive():
                    LOG.error(f"Audio Producer still alive!")
        except RuntimeError as e:
            LOG.exception(e)
        try:
            if self.audio_consumer and self.audio_consumer.is_alive():
                self.audio_consumer.join(1)
                if self.audio_consumer.is_alive():
                    LOG.error(f"Audio Consumer still alive!")
        except RuntimeError as e:
            LOG.exception(e)
