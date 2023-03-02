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

import json
import os
import shutil
import sys
import unittest

from os.path import dirname, join
from threading import Thread, Event

CONFIG_PATH = os.path.join(dirname(__file__), "config")
os.environ["XDG_CONFIG_HOME"] = CONFIG_PATH
from ovos_config.config import update_mycroft_config
from mycroft_bus_client import Message
from ovos_utils.log import LOG
from ovos_utils.messagebus import FakeBus
from speech_recognition import AudioData

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


class UtilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.makedirs(join(CONFIG_PATH, "neon"), exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.path.exists(CONFIG_PATH):
            shutil.rmtree(CONFIG_PATH)

    def test_use_neon_speech(self):
        from neon_speech.utils import use_neon_speech
        test_args = ("one", 1, True)

        def _wrapped_method(*args):
            import inspect

            stack = inspect.stack()
            mod = inspect.getmodule(stack[1][0])
            name = mod.__name__.split('.')[0]
            self.assertEqual(name, "neon_speech")
            self.assertEqual(args, test_args)

        use_neon_speech(_wrapped_method)(*test_args)

    def test_install_stt_plugin(self):
        from neon_speech.utils import install_stt_plugin
        self.assertTrue(install_stt_plugin(
            "ovos-stt-plugin-vosk"))
        import ovos_stt_plugin_vosk

    def test_patch_config(self):
        from neon_speech.utils import use_neon_speech
        from neon_utils.configuration_utils import init_config_dir
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
        use_neon_speech(init_config_dir)()

        with open(join(test_config_dir, "OpenVoiceOS", 'ovos.conf')) as f:
            ovos_conf = json.load(f)
        self.assertEqual(ovos_conf['submodule_mappings']['neon_speech'],
                         "neon_core")
        self.assertIsInstance(ovos_conf['module_overrides']['neon_core'], dict)

        from neon_speech.utils import patch_config
        import yaml
        test_config = {"new_key": {'val': True}}
        patch_config(test_config)
        conf_file = os.path.join(test_config_dir, 'neon',
                                 'neon.yaml')
        self.assertTrue(os.path.isfile(conf_file))
        with open(conf_file) as f:
            config = yaml.safe_load(f)

        self.assertTrue(config['new_key']['val'])
        shutil.rmtree(test_config_dir)
        os.environ.pop("XDG_CONFIG_HOME")

    def test_get_stt_from_file(self):
        from neon_speech.service import NeonSpeechClient
        from neon_speech.utils import use_neon_speech
        from neon_messagebus.service import NeonBusService
        from ovos_config.config import Configuration
        AUDIO_FILE_PATH = os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "audio_files")
        TEST_CONFIG = use_neon_speech(Configuration)()
        TEST_CONFIG["stt"]["module"] = "deepspeech_stream_local"
        bus = NeonBusService(daemonic=True)
        bus.start()
        client = NeonSpeechClient(speech_config=TEST_CONFIG, daemonic=True)
        audio, context, transcripts = \
            client._get_stt_from_file(join(AUDIO_FILE_PATH, "stop.wav"))
        self.assertIsInstance(audio, AudioData)
        self.assertIsInstance(context, dict)
        self.assertIsInstance(transcripts, list)
        self.assertIn("stop", transcripts)

        def threaded_get_stt():
            audio, context, transcripts = \
                client._get_stt_from_file(join(AUDIO_FILE_PATH, "stop.wav"))
            self.assertIsInstance(audio, AudioData)
            self.assertIsInstance(context, dict)
            self.assertIsInstance(transcripts, list)
            self.assertIn("stop", transcripts)

        threads = list()
        for i in range(0, 12):
            t = Thread(target=threaded_get_stt)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(30)
        try:
            bus.shutdown()
        except Exception as e:
            LOG.error(e)
    # TODO: Test other speech service methods directly

    def test_ovos_plugin_compat(self):
        from neon_speech.stt import STTFactory
        ovos_vosk_streaming = STTFactory().create(
            {'module': 'ovos-stt-plugin-vosk-streaming',
             'lang': 'en-us'})
        self.assertIsInstance(ovos_vosk_streaming.results_event, Event)
        test_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                 "audio_files", "stop.wav")
        from neon_utils.file_utils import get_audio_file_stream
        audio_stream = get_audio_file_stream(test_file)
        ovos_vosk_streaming.stream_start('en-us')
        while True:
            try:
                ovos_vosk_streaming.stream_data(audio_stream.read(1024))
            except EOFError:
                break
        transcriptions = ovos_vosk_streaming.stream_stop()
        self.assertIsInstance(transcriptions, list)
        self.assertIsInstance(transcriptions[0], str)


class ServiceTests(unittest.TestCase):
    bus = FakeBus()
    bus.connected_event = Event()
    bus.connected_event.set()

    hotwords_config = {
        "hey_neon": {
            "module": "ovos-ww-plugin-vosk",
            "rule": "fuzzy",
            "listen": True
        },
        "hey_mycroft": {
            "active": False,
            "module": "ovos-ww-plugin-vosk",
            "model": None,  # TODO: Patching default config merge
            "rule": "fuzzy",
            "listen": True
        },
        "wake_up": {
            "active": False,
            "module": "ovos-ww-plugin-vosk",
            "rule": "fuzzy"
        }
    }

    @classmethod
    def setUpClass(cls):
        from neon_utils.configuration_utils import init_config_dir
        init_config_dir()

        update_mycroft_config({"hotwords": cls.hotwords_config})
        # assert os.path.isfile(join(test_config_dir, "neon", "neon.yaml"))
        import importlib
        import ovos_config.config
        importlib.reload(ovos_config.config)
        # from ovos_config.config import Configuration
        # assert Configuration.xdg_configs[0]['hotwords'] == hotwords_config

        from neon_speech.utils import use_neon_speech
        use_neon_speech(init_config_dir)()
        from neon_speech.service import NeonSpeechClient
        cls.service = NeonSpeechClient(bus=cls.bus)
        # assert Configuration() == service.loop.config_core

        cls.service.start()
        cls.service.loop.config_loaded.wait(30)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.shutdown()
        if os.path.exists(CONFIG_PATH):
            shutil.rmtree(CONFIG_PATH)

    def test_loop_events(self):
        from mycroft.listener import RecognizerLoop
        self.assertIsInstance(self.service.loop, RecognizerLoop)
        for event in ["recognizer_loop:utterance",
                      "recognizer_loop:speech.recognition.unknown",
                      "recognizer_loop:awoken", "recognizer_loop:wakeword",
                      "recognizer_loop:hotword", "recognizer_loop:stopword",
                      "recognizer_loop:wakeupword",
                      "recognizer_loop:record_end",
                      "recognizer_loop:no_internet",
                      "recognizer_loop:hotword_event"]:
            self.assertEqual(len(self.service.loop.listeners(event)), 1)

    def test_bus_events(self):
        self.assertEqual(self.service.bus, self.bus)
        for event in ["open", "recognizer_loop:sleep",
                      "recognizer_loop:wake_up", "recognizer_loop:record_stop",
                      "recognizer_loop:state.set", "recognizer_loop:state.get",
                      "mycroft.mic.mute", "mycroft.mic.unmute",
                      "mycroft.mic.get_status", "mycroft.mic.listen",
                      "mycroft.paired", "recognizer_loop:audio_output_start",
                      "mycroft.stop", "ovos.languages.stt",
                      "intent.service.skills.activated", "opm.stt.query",
                      "opm.ww.query", "opm.vad.query",
                      # Neon Listeners
                      "mycroft.internet.connected",
                      "ovos.phal.wifi.plugin.fully_offline", "mycroft.ready",
                      "neon.get_stt", "neon.audio_input",
                      "neon.wake_words_state", "neon.query_wake_words_state",
                      "neon.profile_update", "neon.get_wake_words",
                      "neon.enable_wake_word", "neon.disable_wake_word"]:
            self.assertEqual(len(self.bus.ee.listeners(event)), 1)

    def test_get_wake_words(self):
        resp = self.bus.wait_for_response(Message("neon.get_wake_words"),
                                          "neon.wake_words")
        self.assertIsInstance(resp, Message)
        self.assertEqual({"hey_neon", "hey_mycroft"}, set(resp.data.keys()))

        # Test Main WW is active
        config_patch = {"listener": {"wake_word": "hey_neon"},
                        "hotwords": {"hey_neon": {"active": None}}}
        update_mycroft_config(config_patch, bus=self.bus)
        self.service.loop.config_loaded.wait(60)
        self.assertIsNone(self.service.loop.config_core
                          ['hotwords']['hey_neon']['active'])
        self.assertEqual(self.service.loop.config_core['listener']['wake_word'],
                         "hey_neon")
        resp = self.bus.wait_for_response(Message("neon.get_wake_words"),
                                          "neon.wake_words")
        self.assertIsInstance(resp, Message)
        self.assertEqual({"hey_neon", "hey_mycroft"}, set(resp.data.keys()))
        self.assertTrue(resp.data['hey_neon']['active'])

    def test_disable_wake_word(self):
        hotword_config = dict(self.hotwords_config)
        hotword_config['hey_mycroft']['active'] = True
        # hotword_config['hey_neon']['active'] = None
        hotword_config['wake_up']['active'] = False
        self.service.loop.config_loaded.clear()
        update_mycroft_config({"hotwords": hotword_config}, bus=self.bus)
        self.service.loop.config_loaded.wait(60)
        self.assertTrue(self.service.loop.config_core
                        ['hotwords']['hey_mycroft']['active'])
        self.assertTrue(self.service.loop.config_core
                        ['hotwords']['hey_neon']['active'])
        self.assertFalse(self.service.loop.config_core
                         ['hotwords']['wake_up']['active'])
        self.assertEqual(set(self.service.loop.engines.keys()),
                         {'hey_neon', "hey_mycroft"},
                         self.service.config['hotwords'])

        # Test Disable Valid
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": False, "active": False,
                                     "wake_word": "hey_mycroft"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()), {'hey_neon'})

        # Test Disable already disabled
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already disabled",
                                     "active": False,
                                     "wake_word": "hey_mycroft"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()), {'hey_neon'})

        # Test Disable only active
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_neon"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "only one active ww",
                                     "active": True,
                                     "wake_word": "hey_neon"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()), {'hey_neon'})

        # Test Disable invalid word
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "wake_up"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already disabled",
                                     "active": False,
                                     "wake_word": "wake_up"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()), {'hey_neon'})

    def test_enable_wake_word(self):
        hotword_config = dict(self.hotwords_config)
        hotword_config['hey_mycroft']['active'] = False
        hotword_config['hey_neon']['active'] = True
        hotword_config['wake_up']['active'] = False
        self.service.loop.config_loaded.clear()
        update_mycroft_config({"hotwords": hotword_config}, bus=self.bus)
        self.service.loop.config_loaded.wait(60)
        self.assertFalse(self.service.loop.config_core
                         ['hotwords']['hey_mycroft']['active'])
        self.assertTrue(self.service.loop.config_core
                        ['hotwords']['hey_neon']['active'])
        self.assertFalse(self.service.loop.config_core
                         ['hotwords']['wake_up']['active'])

        self.assertEqual(set(self.service.loop.engines.keys()),
                         {'hey_neon'}, self.service.config['hotwords'])
        # Test Enable valid
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": False,
                                     "active": True,
                                     "wake_word": "hey_mycroft"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])

        # Test Enable already enabled
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already enabled",
                                     "active": True,
                                     "wake_word": "hey_mycroft"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])

        # Test Enable invalid word
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "wake_up"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww not configured",
                                     "active": False,
                                     "wake_word": "wake_up"})
        self.assertTrue(self.service.loop.config_loaded.isSet())
        self.assertEqual(set(self.service.loop.engines.keys()),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])


if __name__ == '__main__':
    unittest.main()
