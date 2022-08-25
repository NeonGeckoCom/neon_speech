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

import os
from tempfile import mkstemp

from threading import Thread, Lock
from time import time

from ovos_utils.process_utils import StatusCallbackMap, ProcessStatus
from pydub import AudioSegment
from speech_recognition import AudioData

from neon_utils.file_utils import decode_base64_string_to_file
from neon_utils.messagebus_utils import get_messagebus
from neon_utils.logger import LOG
from neon_utils.configuration_utils import get_neon_user_config
from neon_utils.user_utils import apply_local_user_profile_updates
from ovos_utils.json_helper import merge_dict
from mycroft_bus_client import Message

from mycroft.client.speech.service import SpeechService
from ovos_config.config import Configuration
from neon_speech.listener import NeonRecognizerLoop
from neon_speech.stt import STTFactory


def on_ready():
    LOG.info('Speech client is ready.')


def on_stopping():
    LOG.info('Speech service is shutting down...')


def on_error(e='Unknown'):
    LOG.error('Audio service failed to launch ({}).'.format(repr(e)))


def on_alive():
    LOG.debug("Speech client alive")


def on_started():
    LOG.debug("Speech client started")


class NeonSpeechClient(SpeechService):
    def __init__(self, ready_hook=on_ready, error_hook=on_error,
                 stopping_hook=on_stopping, alive_hook=on_alive,
                 started_hook=on_started, watchdog=lambda: None,
                 speech_config=None, daemonic=False):
        """
        Creates a Speech service thread
        :param ready_hook: function callback when service is ready
        :param error_hook: function callback to handle uncaught exceptions
        :param stopping_hook: function callback when service is stopping
        :param alive_hook: function callback when service is alive
        :param started_hook: function callback when service is started
        :param speech_config: DEPRECATED global core configuration override
        :param daemonic: if True, run this thread as a daemon
        """
        if speech_config:
            LOG.info("Updating global config with passed config")
            from neon_speech.utils import patch_config
            patch_config(speech_config)
        # Don't init SpeechClient, because we're overriding self.loop
        Thread.__init__(self)
        self.setDaemon(daemonic)
        # Init messagebus and handlers
        self.bus = get_messagebus()
        from neon_utils.signal_utils import init_signal_handlers, \
            init_signal_bus
        init_signal_bus(self.bus)
        init_signal_handlers()

        self._default_user = get_neon_user_config()
        self._default_user['user']['username'] = "local"

        self.config = Configuration()
        self.lock = Lock()

        callbacks = StatusCallbackMap(on_ready=ready_hook, on_error=error_hook,
                                      on_stopping=stopping_hook,
                                      on_alive=alive_hook,
                                      on_started=started_hook)
        self.status = ProcessStatus('speech', self.bus, callbacks)
        self.status.set_started()
        self.status.bind(self.bus)
        self.loop = NeonRecognizerLoop(self.bus, watchdog)
        self.connect_loop_events()
        self.connect_bus_events()
        LOG.info(f"Creating `api_stt` object for messagebus API calls")
        self.api_stt = STTFactory.create(config=self.config,
                                         results_event=None)

    def shutdown(self):
        self.status.set_stopping()
        self.loop.stop()

    def connect_bus_events(self):
        super(NeonSpeechClient, self).connect_bus_events()
        # Register handler for internet (re-)connection
        # TODO: This should be defined as a single event DM
        self.bus.on("mycroft.internet.connected",
                    self.handle_internet_connected)
        self.bus.on("ovos.wifi.setup.completed",
                    self.handle_internet_connected)

        # Register API Handlers
        self.bus.on("neon.get_stt", self.handle_get_stt)
        self.bus.on("neon.audio_input", self.handle_audio_input)

        # Language Support Bus API
        self.bus.on("neon.get_languages_stt", self.handle_get_languages_stt)

        # State Change Notifications
        self.bus.on("neon.wake_words_state", self.handle_wake_words_state)
        self.bus.on("neon.query_wake_words_state",
                    self.handle_query_wake_words_state)
        self.bus.on("neon.profile_update", self.handle_profile_update)

    def handle_get_languages_stt(self, message):
        """
        Handle a request for supported STT languages
        :param message: neon.get_languages_stt request
        """
        stt_langs = self.loop.stt.available_languages or \
            [self.config.get('language', {}).get('user') or 'en-us']
        LOG.info(f"Got stt_langs: {stt_langs}")
        self.bus.emit(message.response({'stt_langs': stt_langs}))

    def handle_profile_update(self, message):
        """
        Handle an emitted profile update. If username associated with update is
        "local", updates the default profile applied to audio input messages.
        :param message: Message associated with profile update
        """
        updated_profile = message.data.get("profile")
        if updated_profile["user"]["username"] == \
                self._default_user["user"]["username"]:
            apply_local_user_profile_updates(updated_profile,
                                             self._default_user)

    def handle_utterance(self, event: dict):
        """
        Handle an utterance event on the Recognizer Loop
        :param event: Utterance event
        """
        LOG.info("Utterance: " + str(event['utterances']))
        context = event["context"]  # from audio transformers
        context.update({'client_name': 'mycroft_listener',
                        'source': 'audio',
                        'ident': event.pop('ident', str(round(time()))),
                        'raw_audio': event.pop('raw_audio', None),
                        'destination': ["skills"],
                        "timing": event.pop("timing", {}),
                        'username': self._default_user["user"]["username"],
                        'user_profiles': [self._default_user.content]
                        })
        if "data" in event:
            data = event.pop("data")
            context = merge_dict(context, data)

        self._emit_utterance_to_skills(Message('recognizer_loop:utterance',
                                               event, context))

    def handle_wake_words_state(self, message):
        """
        Handle a change of WW state
        :param message: Message associated with request
        """
        enabled = message.data.get("enabled", True)
        self.loop.responsive_recognizer.use_wake_word = enabled

    def handle_query_wake_words_state(self, message):
        """
        Query the current WW state
        :param message: Message associated with request
        """
        enabled = self.loop.responsive_recognizer.use_wake_word
        self.bus.emit(message.response({"enabled": enabled}))

    def handle_get_stt(self, message: Message):
        """
        Handles a request for stt.
        Emits a response to the sender with stt data or error data
        :param message: Message associated with request
        """
        if message.data.get("audio_data"):
            wav_file_path = self._write_encoded_file(
                message.data.pop("audio_data"))
        else:
            wav_file_path = message.data.get("audio_file")
        lang = message.data.get("lang")
        ident = message.context.get("ident") or "neon.get_stt.response"
        LOG.info(f"Handling STT request: {ident}")
        if not wav_file_path:
            self.bus.emit(message.reply(
                ident, data={"error": f"audio_file not specified!"}))
            return

        if not os.path.isfile(wav_file_path):
            self.bus.emit(message.reply(
                ident, data={"error": f"{wav_file_path} Not found!"}))

        try:
            _, parser_data, transcriptions = \
                self._get_stt_from_file(wav_file_path, lang)
            self.bus.emit(message.reply(ident,
                                        data={"parser_data": parser_data,
                                              "transcripts": transcriptions}))
        except Exception as e:
            LOG.error(e)
            self.bus.emit(message.reply(ident, data={"error": repr(e)}))

    def handle_audio_input(self, message):
        """
        Handler for `neon.audio_input`.
        Handles remote audio input to Neon and replies with confirmation
        :param message: Message associated with request
        """

        def build_context(msg: Message):
            ctx: dict = message.context
            defaults = {'client_name': 'mycroft_listener',
                        'client': 'api',
                        'source': 'speech_api',
                        'ident': time(),
                        'username': self._default_user["user"]["username"] or
                        "local",
                        'user_profiles': [self._default_user.content]}
            ctx = {**defaults, **ctx, 'destination': ['skills'],
                   'timing': {'start': msg.data.get('time'),
                              'transcribed': time()}}
            return ctx

        ident = message.context.get("ident") or "neon.audio_input.response"
        LOG.info(f"Handling audio input: {ident}")
        if message.data.get("audio_data"):
            wav_file_path = self._write_encoded_file(
                message.data.pop("audio_data"))
        else:
            wav_file_path = message.data.get("audio_file")
        lang = message.data.get("lang")
        try:
            _, parser_data, transcriptions = \
                self._get_stt_from_file(wav_file_path, lang)
            message.context["audio_parser_data"] = parser_data
            context = build_context(message)
            data = {
                "utterances": transcriptions,
                "lang": message.data.get("lang", "en-us")
            }
            handled = self._emit_utterance_to_skills(Message(
                'recognizer_loop:utterance', data, context))
            self.bus.emit(message.reply(ident,
                                        data={"parser_data": parser_data,
                                              "transcripts": transcriptions,
                                              "skills_recv": handled}))
        except Exception as e:
            LOG.error(e)
            self.bus.emit(message.reply(ident, data={"error": repr(e)}))

    def handle_internet_connected(self, _):
        """
        Handle notification from core that internet connection is established
        """
        LOG.info(f"Internet Connected, Resetting STT Stream")
        self.loop.audio_producer.stream_handler.has_result.set()

    @staticmethod
    def _write_encoded_file(audio_data: str) -> str:
        _, output_path = mkstemp()
        if os.path.isfile(output_path):
            os.remove(output_path)
        wav_file_path = decode_base64_string_to_file(audio_data, output_path)
        return wav_file_path

    def _get_stt_from_file(self, wav_file: str,
                           lang: str = None) -> (AudioData, dict, list):
        """
        Performs STT and audio processing on the specified wav_file
        :param wav_file: wav audio file to process
        :param lang: language of passed audio
        :return: (AudioData of object, extracted context, transcriptions)
        """
        from neon_utils.file_utils import get_audio_file_stream
        lang = lang or 'en-us'  # TODO: read default from config
        segment = AudioSegment.from_file(wav_file)
        audio_data = AudioData(segment.raw_data, segment.frame_rate,
                               segment.sample_width)
        audio_stream = get_audio_file_stream(wav_file)
        if self.lock.acquire(True, 30):
            LOG.info(f"Starting STT processing (lang={lang}): {wav_file}")
            self.api_stt.stream_start(lang)
            while True:
                try:
                    data = audio_stream.read(1024)
                    self.api_stt.stream_data(data)
                except EOFError:
                    break
            transcriptions = self.api_stt.stream_stop()
            self.lock.release()
        else:
            LOG.error(f"Timed out acquiring lock, not processing: {wav_file}")
            transcriptions = []
        if isinstance(transcriptions, str):
            LOG.warning("Transcriptions is a str, no alternatives provided")
            transcriptions = [transcriptions]
        audio, audio_context = self.loop.responsive_recognizer. \
            audio_consumers.transform(audio_data)
        LOG.info(f"Transcribed: {transcriptions}")
        return audio, audio_context, transcriptions

    def _emit_utterance_to_skills(self, message_to_emit: Message) -> bool:
        """
        Emits a message containing a user utterance to skills for intent
        processing and checks that it is received by the skills module.
        :param message_to_emit: utterance message to send
        :return: True if skills module received input, else False
        """
        # Emit single intent request
        ident = message_to_emit.context['ident']
        resp = self.bus.wait_for_response(message_to_emit, timeout=10)
        if not resp:
            LOG.error(f"Skills didn't handle {ident}!")
            return False
        return True
