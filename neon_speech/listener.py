# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending
#
# This software is an enhanced derivation of the Mycroft Project which is licensed under the
# Apache software Foundation software license 2.0 https://www.apache.org/licenses/LICENSE-2.0
# Changes Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import time
from threading import Thread, Event
import speech_recognition as sr
import pyaudio
from queue import Queue, Empty
import json
from pyee import EventEmitter
from requests import RequestException
from requests.exceptions import ConnectionError

from neon_speech.hotword_factory import HotWordFactory
from neon_speech.mic import MutableMicrophone, ResponsiveRecognizer
from neon_speech.utils import find_input_device, get_config
from neon_speech.stt import STTFactory
from ovos_utils.log import LOG

try:
    from NGI.server.chat_user_database import KlatUserDatabase
    from mycroft import device
except Exception as e:
    LOG.error(e)
    device = "desktop"

MAX_MIC_RESTARTS = 20

AUDIO_DATA = 0
STREAM_START = 1
STREAM_DATA = 2
STREAM_STOP = 3


class AudioStreamHandler(object):
    """
    Handles audio stream routing for StreamingSTT classes. The wakeword recognizer will call sream_start when a wake
    word is detected, then call stream_chunk with all audio chunks captured before calling stream_stop after meeting
    recording length or silence thresholds.
    """

    def __init__(self, stream_queue, results_event: Event):
        self.queue = stream_queue
        self.has_result = results_event

    def stream_start(self):
        """
        Add an item to the queue to notify STT we are opening an audio stream.
        """
        self.queue.put((STREAM_START, None, None))

    def stream_chunk(self, chunk):
        """
        Add an audio chunk to the queue for STT to process
        :param chunk: audio chunk from mic to be processed
        """
        self.queue.put((STREAM_DATA, chunk, None))

    def stream_stop(self):
        """
        Add an item to the queue to notify STT the audio stream is ended and to generate the transcription.
        """
        self.queue.put((STREAM_STOP, None, None))


class AudioProducer(Thread):
    """
    AudioProducer
    Given a mic and a recognizer implementation, continuously listens to the
    mic for potential speech chunks and pushes them onto the queue.
    """

    def __init__(self, state, producer_queue, mic, recognizer, emitter, stream_handler):
        super(AudioProducer, self).__init__()
        self.daemon = True
        self.state = state
        self.queue = producer_queue
        self.mic = mic
        self.recognizer = recognizer
        self.emitter = emitter
        self.stream_handler = stream_handler

    def run(self):
        """
        This is the mic is passed into the recognizer for WW recognition or continuous STT streaming. Audio chunks
        for STT are generated here and passed to AudioConsumer when a phrase is completed.
        """
        restart_attempts = 0
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source)
            while self.state.running:
                try:
                    audio = self.recognizer.listen(source, self.emitter,
                                                   self.stream_handler)
                    if audio is not None:
                        audio, context = \
                            self.recognizer.audio_consumers.get_context(audio)
                        self.queue.put((AUDIO_DATA, audio, context))
                    else:
                        LOG.warning("Audio contains no data.")
                except IOError as e:
                    # IOError will be thrown if the read is unsuccessful.
                    # If self.recognizer.overflow_exc is False (default)
                    # input buffer overflow IOErrors due to not consuming the
                    # buffers quickly enough will be silently ignored.
                    LOG.exception('IOError Exception in AudioProducer')
                    if e.errno == pyaudio.paInputOverflowed:
                        pass  # Ignore overflow errors
                    elif restart_attempts < MAX_MIC_RESTARTS:
                        # restart the mic
                        restart_attempts += 1
                        LOG.info('Restarting the microphone...')
                        source.restart()
                        LOG.info('Restarted...')
                    else:
                        LOG.error('Restarting mic doesn\'t seem to work. '
                                  'Stopping...')
                        raise
                except Exception:
                    LOG.exception('Exception in AudioProducer')
                    raise
                else:
                    # Reset restart attempt counter on sucessful audio read
                    restart_attempts = 0
                finally:
                    if self.stream_handler is not None:
                        self.stream_handler.stream_stop()

    def stop(self):
        """
            Stop producer thread.
        """
        self.state.running = False
        self.recognizer.stop()


class AudioConsumer(Thread):
    """
    AudioConsumer
    Consumes AudioData chunks off the queue
    """

    # In seconds, the minimum audio size to be sent to remote STT
    MIN_AUDIO_SIZE = 0.5

    def __init__(self, state, consumer_queue, emitter, stt, wakeup_recognizer):
        super(AudioConsumer, self).__init__()
        self.daemon = True
        self.queue = consumer_queue
        self.state = state
        self.emitter = emitter
        self.config = emitter.config
        self.stt = stt
        self.wakeup_recognizer = wakeup_recognizer
        self.use_wake_words = self.config.get("wake_word_enabled", True)

        # TODO: Revisit after user database #24 DM
        if device == "server":
            self.chat_user_database = KlatUserDatabase()
        else:
            self.chat_user_database = None

    def run(self):
        while self.state.running:
            self.read()

    def read(self):
        try:
            message = self.queue.get(timeout=0.5)
        except Empty:
            return

        if message is None:
            return

        tag, data, context = message

        if tag == AUDIO_DATA:
            if data is not None:
                if self.state.sleeping:
                    self.wake_up(data)
                else:
                    self.process(data, context)
        elif tag == STREAM_START:
            self.stt.stream_start()
        elif tag == STREAM_DATA:
            self.stt.stream_data(data)
        elif tag == STREAM_STOP:
            self.stt.stream_stop()
        else:
            LOG.error("Unknown audio queue type %r" % message)

    # TODO: Localization
    def wake_up(self, audio):
        """
        Handles wakeup from sleeping state
        :param audio: (AudioData) object associted with wakeup phrase
        """
        if self.wakeup_recognizer.found_wake_word(audio.frame_data):
            self.state.sleeping = False
            self.emitter.emit('recognizer_loop:awoken')

    @staticmethod
    def _audio_length(audio):
        return float(len(audio.frame_data)) / (
                audio.sample_rate * audio.sample_width)

    # TODO: Localization
    def process(self, audio, context=None):
        """
        Handles audio from AudioConsumer after it has been passed through the audio processing modules
        :param audio: (AudioData) raw audio data object
        :param context: (dict) context extracted by processing modules
        """
        context = context or {}
        heard_time = time.time()
        if self._audio_length(audio) < self.MIN_AUDIO_SIZE:
            LOG.warning("Audio too short to be processed")
        else:
            transcriptions = self.transcribe(audio, context)
            transcribed_time = time.time()
            if isinstance(transcriptions, str):
                transcriptions = [transcriptions]
            if transcriptions and transcriptions[0]:
                ident = str(time.time()) + str(hash(transcriptions[0]))
                transcribed_time = time.time()

                # STT succeeded, send the transcribed speech on for processing
                payload = {
                    'utterances': transcriptions,
                    'lang': self.stt.lang,
                    'ident': ident,
                    "data": context,
                    "timing": {"start": heard_time,
                               "transcribed": transcribed_time}
                }
                self.emitter.emit("recognizer_loop:utterance", payload)

    def transcribe(self, audio: sr.AudioData, context: dict):
        """
        Accepts input audio and returns a list of transcript candidates (in original input language)
        :param audio: (AudioData) input audio object
        :return: list of transcription candidates
        """
        def send_unknown_intent():
            """ Send message that nothing was transcribed. """
            if self.use_wake_words:  # Don't capture ambient noise
                self.emitter.emit('recognizer_loop:speech.recognition.unknown')

        try:
            user = context.get("user")
            if self.chat_user_database:
                # self.server_listener.get_nick_profiles(flac_filename)
                self.chat_user_database.update_profile_for_nick(user)
                chat_user = self.chat_user_database.get_profile(user)
                stt_language = chat_user["speech"].get('stt_language', 'en')
                alt_langs = chat_user["speech"].get("alt_languages", ['en', 'es'])
                LOG.debug(stt_language)
            else:
                # TODO: Populate from config DM
                stt_language = None
                alt_langs = None
            if isinstance(audio, sr.AudioData):
                LOG.debug(len(audio.frame_data))
            else:
                LOG.warning(audio)

            # Invoke the STT engine on the audio clip
            transcripts = self.stt.execute(audio)  # This is the STT return here (incl streams)
            LOG.debug(transcripts)
            if isinstance(transcripts, str):
                transcripts = [transcripts.strip()]
            transcripts = [t.strip() for t in transcripts if t.strip()]
            if transcripts is None or len(transcripts) == 1 and not transcripts[0]:
                send_unknown_intent()
                LOG.info('no words were transcribed')
            return transcripts
        except sr.RequestError as e:
            LOG.error("Could not request Speech Recognition {0}".format(e))
        except ConnectionError as e:
            LOG.error("Connection Error: {0}".format(e))

            self.emitter.emit("recognizer_loop:no_internet")
        except RequestException as e:
            LOG.error(e.__class__.__name__ + ': ' + str(e))
        except Exception as e:
            send_unknown_intent()
            LOG.error(e)
            LOG.error("Speech Recognition could not understand audio")
            return None


class RecognizerLoopState:
    def __init__(self):
        self.running = False
        self.sleeping = False


def recognizer_conf_hash(config):
    """Hash of the values important to the listener."""
    c = {
        'listener': config.get('listener'),
        'hotwords': config.get('hotwords'),
        'stt': config.get('stt'),
        'opt_in': config.get('opt_in', False)
    }
    return hash(json.dumps(c, sort_keys=True))


class RecognizerLoop(EventEmitter):
    """ EventEmitter loop running speech recognition.

    Local wake word recognizer and remote general speech recognition.
    """

    def __init__(self, config=None):
        super(RecognizerLoop, self).__init__()
        self.producer = None
        self.consumer = None

        self.mute_calls = 0
        self.config_core = config or get_config()
        # self._config_hash = recognizer_conf_hash(config)
        self.lang = config.get('lang', "en-us")
        self.config = config.get('listener', {})
        rate = self.config.get('sample_rate', 16000)

        device_index = self.config.get('device_index')
        device_name = self.config.get('device_name')
        if not device_index and device_name:
            device_index = find_input_device(device_name)

        LOG.debug('Using microphone (None = default): ' + str(device_index))

        self.microphone = MutableMicrophone(device_index, rate,
                                            mute=self.mute_calls > 0)

        # TODO - localization
        self.wakeup_recognizer = self.create_wakeup_recognizer()
        self.hotword_engines = {}
        self.create_hotword_engines()
        self.responsive_recognizer = ResponsiveRecognizer(
            self.hotword_engines, config)
        self.state = RecognizerLoopState()

    def bind(self, parsers_service):
        self.responsive_recognizer.bind(parsers_service)

    def create_hotword_engines(self):
        LOG.info("creating hotword engines")
        hot_words = self.config_core.get("hotwords", {})
        for word in hot_words:
            data = hot_words[word]
            if word == self.wakeup_recognizer.key_phrase \
                    or not data.get("active", True):
                continue
            sound = data.get("sound")
            utterance = data.get("utterance")
            listen = data.get("listen", False)
            engine = HotWordFactory.create_hotword(
                word, lang=self.lang, loop=self,
                config=self.config_core.get("hotwords"))

            self.hotword_engines[word] = {"engine": engine,
                                          "sound": sound,
                                          "utterance": utterance,
                                          "listen": listen}

    def create_wakeup_recognizer(self):
        LOG.info("creating stand up word engine")
        word = self.config.get("stand_up_word", "wake up")
        return HotWordFactory.create_hotword(
            word, lang=self.lang, loop=self,
            config=self.config_core.get("hotwords"))

    def start_async(self):
        """Start consumer and producer threads."""
        self.state.running = True
        results_event = Event()
        stt = STTFactory.create(results_event = results_event)
        queue = Queue()
        stream_handler = None
        if stt.can_stream:
            stream_handler = AudioStreamHandler(queue, results_event)
        self.producer = AudioProducer(self.state, queue, self.microphone,
                                      self.responsive_recognizer, self,
                                      stream_handler)
        self.producer.start()
        self.consumer = AudioConsumer(self.state, queue, self,
                                      stt, self.wakeup_recognizer)
        self.consumer.start()

    def stop(self):
        self.state.running = False
        self.producer.stop()
        # wait for threads to shutdown
        self.producer.join()
        self.consumer.join()

    def mute(self):
        """
        Mute microphone and increase number of requests to mute
        """
        self.mute_calls += 1
        if self.microphone:
            self.microphone.mute()

    def unmute(self):
        """
        Unmute mic if as many unmute calls as mute calls have been
        received.
        """
        if self.mute_calls > 0:
            self.mute_calls -= 1

        if self.mute_calls <= 0 and self.microphone:
            self.microphone.unmute()
            self.mute_calls = 0

    def force_unmute(self):
        """
        Completely unmute mic regardless of the number of calls to mute.
        """
        self.mute_calls = 0
        self.unmute()

    def is_muted(self):
        if self.microphone:
            return self.microphone.is_muted()
        else:
            return True  # consider 'no mic' muted

    def sleep(self):
        self.state.sleeping = True

    def awaken(self):
        self.state.sleeping = False

    def run(self):
        """Start and reload mic and STT handling threads as needed.

        Wait for KeyboardInterrupt and shutdown cleanly.
        """
        try:
            self.start_async()
        except Exception as x:
            LOG.error(x)
            LOG.exception('Starting producer/consumer threads for listener '
                          'failed.')
            return

        # Handle reload of consumer / producer if config changes
        while self.state.running:
            try:
                time.sleep(1)
            except KeyboardInterrupt as e:
                LOG.error(e)
                self.stop()
                raise  # Re-raise KeyboardInterrupt
            except Exception:
                LOG.exception('Exception in RecognizerLoop')
                raise

    def reload(self):
        """
            Reload configuration and restart consumer and producer
        """
        self.stop()
        for hw in self.hotword_engines:
            try:
                self.hotword_engines[hw]["engine"].stop()
            except Exception as e:
                LOG.exception(e)
        # # load config
        # self._load_config()
        # restart
        self.start_async()

    def change_wake_word_state(self, enabled: bool):
        self.responsive_recognizer.use_wake_word = enabled
        self.consumer.use_wake_words = enabled