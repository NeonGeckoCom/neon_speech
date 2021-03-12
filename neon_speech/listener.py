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
from threading import Thread
import speech_recognition as sr
import pyaudio
from queue import Queue, Empty
import json
from pyee import EventEmitter
from requests import RequestException
from requests.exceptions import ConnectionError

from neon_speech.hotword_factory import HotWordFactory
from neon_speech.mic import MutableMicrophone, ResponsiveRecognizer
from neon_speech.utils import find_input_device
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
    def __init__(self, queue):
        self.queue = queue

    def stream_start(self):
        self.queue.put((STREAM_START, None))

    def stream_chunk(self, chunk):
        self.queue.put((STREAM_DATA, chunk))

    def stream_stop(self):
        self.queue.put((STREAM_STOP, None))


class AudioProducer(Thread):
    """AudioProducer
    Given a mic and a recognizer implementation, continuously listens to the
    mic for potential speech chunks and pushes them onto the queue.
    """

    def __init__(self, state, queue, mic, recognizer, emitter, stream_handler):
        super(AudioProducer, self).__init__()
        self.daemon = True
        self.state = state
        self.queue = queue
        self.mic = mic
        self.recognizer = recognizer
        self.emitter = emitter
        self.stream_handler = stream_handler

    def run(self):
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
        """Stop producer thread."""
        self.state.running = False
        self.recognizer.stop()


class AudioConsumer(Thread):
    """AudioConsumer
    Consumes AudioData chunks off the queue
    """

    # In seconds, the minimum audio size to be sent to remote STT
    MIN_AUDIO_SIZE = 0.5

    def __init__(self, state, queue, emitter, stt, wakeup_recognizer):
        super(AudioConsumer, self).__init__()
        self.daemon = True
        self.queue = queue
        self.state = state
        self.emitter = emitter
        self.stt = stt
        self.wakeup_recognizer = wakeup_recognizer

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
        if self.wakeup_recognizer.found_wake_word(audio.frame_data):
            self.state.sleeping = False
            self.emitter.emit('recognizer_loop:awoken')

    @staticmethod
    def _audio_length(audio):
        return float(len(audio.frame_data)) / (
                audio.sample_rate * audio.sample_width)

    # TODO: Localization
    def process(self, audio, context=None):
        context = context or {}
        heard_time = time.time()
        if self._audio_length(audio) < self.MIN_AUDIO_SIZE:
            LOG.warning("Audio too short to be processed")
        else:
            transcription = self.transcribe(audio, context)
            transcribed_time = time.time()
            if transcription:
                ident = str(time.time()) + str(hash(transcription))
                # STT succeeded, send the transcribed speech on for processing
                payload = {
                    'utterances': [transcription],
                    'lang': self.stt.lang,
                    'ident': ident,
                    "data": context,
                    "timing": {"start": heard_time,
                               "transcribed": transcribed_time}
                }
                self.emitter.emit("recognizer_loop:utterance", payload)

    def transcribe(self, audio: sr.AudioData, context: dict):
        def send_unknown_intent():
            """ Send message that nothing was transcribed. """
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
            text = self.stt.execute(audio, stt_language)
            if text is not None:
                text = text.lower().strip()
                LOG.debug("STT: " + text)
            else:
                send_unknown_intent()
                LOG.info('no words were transcribed')
            return text
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
        self.mute_calls = 0
        self.config_core = config or {}
        self._config_hash = recognizer_conf_hash(config)
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
        def adapt_neon_config() -> dict:
            """
            Temporary fix to adapt old style Neon configuration for single Hotwords
            :return: dict of single wake word config
            """
            LOG.warning("This configuration is depreciated, please update to 'hotwords' configuration")
            if "wake_word" in self.config:
                return {self.config["wake_word"]: {"module": self.config.get('module'),
                                                   "phonemes": self.config.get('phonemes'),
                                                   "threshold": self.config.get('threshold'),
                                                   "lang": self.config.get('language'),
                                                   "sample_rate": self.config.get('rate'),
                                                   "listen": True,
                                                   "sound": "snd/start_listening.wav",
                                                   "local_model_file": self.config.get("precise",
                                                                                       {}).get("local_model_file")}}
            else:
                return {}

        LOG.info("creating hotword engines")
        hot_words = self.config_core.get("hotwords", adapt_neon_config())
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
                config=hot_words)

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
        stt = STTFactory.create()
        queue = Queue()
        stream_handler = None
        if stt.can_stream:
            stream_handler = AudioStreamHandler(queue)
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
        """Mute microphone and increase number of requests to mute."""
        self.mute_calls += 1
        if self.microphone:
            self.microphone.mute()

    def unmute(self):
        """Unmute mic if as many unmute calls as mute calls have been received.
        """
        if self.mute_calls > 0:
            self.mute_calls -= 1

        if self.mute_calls <= 0 and self.microphone:
            self.microphone.unmute()
            self.mute_calls = 0

    def force_unmute(self):
        """Completely unmute mic regardless of the number of calls to mute."""
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
        except Exception:
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
        """Reload configuration and restart consumer and producer."""
        self.stop()
        for hw in self.hotword_engines:
            try:
                self.hotword_engines[hw]["engine"].stop()
            except Exception as e:
                LOG.exception(e)
        # load config
        self._load_config()
        # restart
        self.start_async()
