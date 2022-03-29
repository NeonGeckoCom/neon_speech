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

import os

from threading import Thread, Lock
from time import time
from ovos_utils.process_utils import StatusCallbackMap, ProcessStatus
from pydub import AudioSegment
from speech_recognition import AudioData

from neon_utils.messagebus_utils import get_messagebus
from neon_utils.logger import LOG
from neon_utils.configuration_utils import get_neon_user_config
from ovos_utils.json_helper import merge_dict
from mycroft_bus_client import Message

from mycroft.client.speech.service import SpeechClient

from neon_speech.utils import get_config
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


class NeonSpeechClient(SpeechClient):
    def __init__(self, ready_hook=on_ready, error_hook=on_error,
                 stopping_hook=on_stopping, alive_hook=on_alive,
                 started_hook=on_started, watchdog=lambda: None,
                 speech_config=None):
        Thread.__init__(self)

        # Init messagebus and handlers
        self.bus = get_messagebus()
        from neon_utils.signal_utils import init_signal_handlers, init_signal_bus
        init_signal_bus(self.bus)
        init_signal_handlers()

        self.user_config = get_neon_user_config()
        self.config = speech_config or get_config()
        self.lock = Lock()

        callbacks = StatusCallbackMap(on_ready=ready_hook, on_error=error_hook,
                                      on_stopping=stopping_hook,
                                      on_alive=alive_hook, on_started=started_hook)
        self.status = ProcessStatus('speech', self.bus, callbacks)
        self.status.bind(self.bus)
        self.loop = NeonRecognizerLoop(self.bus, watchdog)
        self.connect_loop_events()
        self.connect_bus_events()
        self.api_stt = STTFactory.create(config=self.config,
                                         results_event=None)

    def shutdown(self):
        self.status.set_stopping()
        self.loop.stop()

    def connect_bus_events(self):
        super(NeonSpeechClient, self).connect_bus_events()
        # Register handler for internet (re-)connection
        # TODO: This should be defined as a single event DM
        self.bus.on("mycroft.internet.connected", self.handle_internet_connected)
        self.bus.on("ovos.wifi.setup.completed", self.handle_internet_connected)

        # Register API Handlers
        self.bus.on("neon.get_stt", self.handle_get_stt)
        self.bus.on("neon.audio_input", self.handle_audio_input)

        # State Change Notifications
        self.bus.on("neon.wake_words_state", self.handle_wake_words_state)

    def handle_utterance(self, event):
        LOG.info("Utterance: " + str(event['utterances']))
        context = event["context"]  # from audio transformers
        context.update({'client_name': 'mycroft_listener',
                        'source': 'audio',
                        'ident': event.pop('ident', str(round(time()))),
                        'raw_audio': event.pop('raw_audio', None),
                        'destination': ["skills"],
                        "timing": event.pop("timing", {}),
                        'username': self.user_config["user"]["username"] or
                                    "local",
                        'user_profiles': [self.user_config.content]
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

    def handle_get_stt(self, message: Message):
        """
        Handles a request for stt. Emits a response to the sender with stt data or error data
        :param message: Message associated with request
        """
        wav_file_path = message.data.get("audio_file")
        lang = message.data.get("lang")
        ident = message.context.get("ident") or "neon.get_stt.response"
        if not wav_file_path:
            self.bus.emit(message.reply(ident, data={"error": f"audio_file not specified!"}))
            return

        if not os.path.isfile(wav_file_path):
            self.bus.emit(message.reply(ident, data={"error": f"{wav_file_path} Not found!"}))

        try:
            _, parser_data, transcriptions = self._get_stt_from_file(wav_file_path, lang)
            self.bus.emit(message.reply(ident, data={"parser_data": parser_data, "transcripts": transcriptions}))
        except Exception as e:
            LOG.error(e)
            self.bus.emit(message.reply(ident, data={"error": repr(e)}))

    def handle_audio_input(self, message):
        """
        Handler for `neon.audio_input`. Handles remote audio input to Neon and replies with confirmation
        :param message: Message associated with request
        """

        def build_context(msg: Message):
            ctx: dict = message.context
            defaults = {'client_name': 'mycroft_listener',
                        'client': 'api',
                        'source': 'speech_api',
                        'ident': time(),
                        'username': self.user_config["user"]["username"] or
                                    "local",
                        'user_profiles': [self.user_config.content]}
            ctx = {**defaults, **ctx, 'destination': ['skills'],
                   'timing': {'start': msg.data.get('time'),
                              'transcribed': time()}}
            return ctx

        ident = message.context.get("ident") or "neon.audio_input.response"
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
        Handle notification from core that internet connection has been established
        """
        LOG.info(f"Internet Connected, Resetting STT Stream")
        self.loop.audio_producer.stream_handler.has_result.set()

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
        with self.lock:
            self.api_stt.stream_start(lang)
            while True:
                try:
                    data = audio_stream.read(1024)
                    self.api_stt.stream_data(data)
                except EOFError:
                    break
            transcriptions = self.api_stt.stream_stop()
        if isinstance(transcriptions, str):
            LOG.warning("Transcriptions is a str, no alternatives provided")
            transcriptions = [transcriptions]
        audio, audio_context = self.loop.responsive_recognizer.\
            audio_consumers.transform(audio_data)
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
