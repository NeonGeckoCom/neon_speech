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

import json
import os
import shutil
import sys
import unittest

from os.path import dirname, join
from threading import Thread, Event
from ovos_bus_client import Message
from ovos_utils.messagebus import FakeBus
from speech_recognition import AudioData

CONFIG_PATH = os.path.join(dirname(__file__), "config")
os.environ["XDG_CONFIG_HOME"] = CONFIG_PATH


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
        from ovos_config.locations import USER_CONFIG
        import yaml
        test_config = {"new_key": {'val': True}}
        patch_config(test_config)
        conf_file = os.path.join(test_config_dir, 'neon',
                                 'neon.yaml')
        self.assertEqual(USER_CONFIG, conf_file)
        self.assertTrue(os.path.isfile(conf_file))
        with open(conf_file) as f:
            config = yaml.safe_load(f)

        self.assertTrue(config['new_key']['val'])
        shutil.rmtree(test_config_dir)
        os.environ.pop("XDG_CONFIG_HOME")

    def test_get_stt_from_file(self):
        from neon_speech.service import NeonSpeechClient
        from neon_speech.utils import use_neon_speech
        from ovos_config.config import Configuration
        AUDIO_FILE_PATH = os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "audio_files")
        TEST_CONFIG = use_neon_speech(Configuration)()
        TEST_CONFIG["stt"]["module"] = "deepspeech_stream_local"
        bus = FakeBus()
        bus.connected_event = Event()
        bus.connected_event.set()
        client = NeonSpeechClient(speech_config=TEST_CONFIG, daemonic=True,
                                  bus=bus)
        self.assertIsInstance(client, NeonSpeechClient)
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

    # TODO: Test other speech service methods directly

    def test_ovos_plugin_compat(self):
        from neon_speech.stt import STTFactory
        from ovos_plugin_manager.templates.stt import STT
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

        non_streaming = STTFactory().create(
            {"module": "ovos-stt-plugin-server",
             "ovos-stt-plugin-server": {"url": "https://0.0.0.0:8080/stt"}}
        )
        self.assertIsInstance(non_streaming, STT)
        self.assertEqual(non_streaming.url, "https://0.0.0.0:8080/stt")


class ServiceTests(unittest.TestCase):
    bus = FakeBus()
    bus.connected_event = Event()
    bus.connected_event.set()

    ready_event = Event()

    @classmethod
    def on_ready(cls):
        cls.ready_event.set()

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
        },
        # Patching default hotwords config
        "hey_mycroft_vosk": {
            "listen": False,
            "active": False
        },
        "hey_mycroft_precise": {
            "listen": False,
            "active": False
        },
        "hey_mycroft_pocketsphinx": {
            "listen": False,
            "active": False
        }
    }

    @classmethod
    def setUpClass(cls):
        from ovos_config.config import update_mycroft_config
        from neon_utils.configuration_utils import init_config_dir
        init_config_dir()

        update_mycroft_config({"hotwords": cls.hotwords_config,
                               "stt": {"module": "neon-stt-plugin-nemo"},
                               "VAD": {"module": "dummy"}})
        import importlib
        import ovos_config.config
        importlib.reload(ovos_config.config)
        # from ovos_config.config import Configuration
        # assert Configuration.xdg_configs[0]['hotwords'] == hotwords_config

        from neon_speech.utils import use_neon_speech
        use_neon_speech(init_config_dir)()
        from neon_speech.service import NeonSpeechClient
        cls.service = NeonSpeechClient(bus=cls.bus, ready_hook=cls.on_ready)
        # assert Configuration() == service.loop.config_core

        def _mocked_run():
            stopping_event = Event()
            while cls.service.voice_loop._is_running:
                stopping_event.wait(1)

        cls.service.voice_loop.run = _mocked_run
        cls.service.start()
        cls.ready_event.wait(60)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.shutdown()
        if os.path.exists(CONFIG_PATH):
            shutil.rmtree(CONFIG_PATH)

    def test_bus_events(self):
        self.assertEqual(self.service.bus, self.bus)
        for event in ["recognizer_loop:sleep",
                      "recognizer_loop:wake_up", "recognizer_loop:record_stop",
                      "recognizer_loop:state.set", "recognizer_loop:state.get",
                      "mycroft.mic.mute", "mycroft.mic.unmute",
                      "mycroft.mic.get_status", "mycroft.mic.listen",
                      "recognizer_loop:audio_output_start",
                      "recognizer_loop:audio_output_end",
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
            num_listeners = 1
            if event == "mycroft.internet.connected":
                # Configuration registers this too
                num_listeners = 2
            self.assertEqual(len(self.bus.ee.listeners(event)), num_listeners,
                             f"{event}: {self.bus.ee.listeners(event)}")

    def test_get_wake_words(self):
        from ovos_config.config import update_mycroft_config

        resp = self.bus.wait_for_response(Message("neon.get_wake_words"),
                                          "neon.wake_words")
        self.assertIsInstance(resp, Message)
        self.assertEqual({"hey_neon", "hey_mycroft"}, set(resp.data.keys()))

        # Test Main WW is active
        config_patch = {
            "listener": {"wake_word": "test_ww"},
            "hotwords": {"test_ww": {"module": "ovos-ww-plugin-vosk",
                                     "rule": "fuzzy",
                                     "listen": True}}}
        self.ready_event.clear()
        update_mycroft_config(config_patch, bus=self.bus)
        self.assertTrue(self.ready_event.wait(30))  # Configuration changed
        self.service.reload_configuration()  # TODO Not auto-reloading?
        self.assertIsNone(self.service.config
                          ['hotwords']['test_ww'].get('active'))
        self.assertEqual(self.service.config['listener']['wake_word'],
                         "test_ww")
        resp = self.bus.wait_for_response(Message("neon.get_wake_words"),
                                          "neon.wake_words")
        self.assertIsInstance(resp, Message)
        self.assertEqual({"hey_neon", "hey_mycroft", "test_ww"},
                         set(resp.data.keys()))
        self.assertTrue(resp.data['test_ww']['active'])

        # Test Main WW disabled
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "test_ww"}))
        self.assertIsInstance(resp, Message)
        self.assertFalse(resp.data['active'])
        self.assertEqual(resp.data['wake_word'], 'test_ww')
        resp = self.bus.wait_for_response(Message("neon.get_wake_words"),
                                          "neon.wake_words")
        self.assertIsInstance(resp, Message)
        self.assertFalse(resp.data['test_ww']['active'])

    def test_disable_wake_word(self):
        from ovos_config.config import update_mycroft_config

        hotword_config = dict(self.hotwords_config)
        hotword_config['hey_mycroft']['active'] = True
        # hotword_config['hey_neon']['active'] = None
        hotword_config['wake_up']['active'] = False

        self.ready_event.clear()
        update_mycroft_config({"hotwords": hotword_config,
                               "listener": {"wake_word": "hey_neon"}},
                              bus=self.bus)
        self.service.reload_configuration()  # TODO Not auto-reloading?
        self.assertTrue(self.ready_event.wait(30))  # Assert Reloaded

        self.assertTrue(self.service.config
                        ['hotwords']['hey_mycroft']['active'])
        self.assertIsNone(self.service.config
                          ['hotwords']['hey_neon'].get('active'))
        self.assertFalse(self.service.config
                         ['hotwords']['wake_up']['active'])
        self.assertEqual(set(self.service.hotwords.ww_names),
                         {'hey_neon', "hey_mycroft"},
                         self.service.hotwords.ww_names)

        # Test Disable Valid
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": False, "active": False,
                                     "wake_word": "hey_mycroft"})
        self.assertEqual(set(self.service.hotwords.ww_names), {'hey_neon'})

        # Test Disable already disabled
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already disabled",
                                     "active": False,
                                     "wake_word": "hey_mycroft"})
        self.assertEqual(set(self.service.hotwords.ww_names), {'hey_neon'})

        # Test Disable only active
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "hey_neon"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "only one active ww",
                                     "active": True,
                                     "wake_word": "hey_neon"})
        self.assertEqual(set(self.service.hotwords.ww_names), {'hey_neon'})

        # Test Disable invalid word
        resp = self.bus.wait_for_response(Message("neon.disable_wake_word",
                                                  {"wake_word": "wake_up"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already disabled",
                                     "active": False,
                                     "wake_word": "wake_up"})
        self.assertEqual(set(self.service.hotwords.ww_names), {'hey_neon'})

    def test_enable_wake_word(self):
        from ovos_config.config import update_mycroft_config

        hotword_config = dict(self.hotwords_config)
        hotword_config['hey_mycroft']['active'] = False
        hotword_config['hey_neon']['active'] = True
        hotword_config['wake_up']['active'] = False
        self.ready_event.clear()
        update_mycroft_config({"hotwords": hotword_config}, bus=self.bus)
        self.service.reload_configuration()  # TODO Not auto-reloading?
        self.assertTrue(self.ready_event.wait(30))  # Assert Reloaded
        self.assertFalse(self.service.config
                         ['hotwords']['hey_mycroft']['active'])
        self.assertTrue(self.service.config
                        ['hotwords']['hey_neon']['active'])
        self.assertFalse(self.service.config
                         ['hotwords']['wake_up']['active'])
        self.assertEqual(set(self.service.hotwords.ww_names),
                         {'hey_neon'}, self.service.config['hotwords'])

        # Test Enable valid
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": False,
                                     "active": True,
                                     "wake_word": "hey_mycroft"})
        self.assertEqual(set(self.service.hotwords.ww_names),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])

        # Test Enable already enabled
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "hey_mycroft"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww already enabled",
                                     "active": True,
                                     "wake_word": "hey_mycroft"})
        self.assertEqual(set(self.service.hotwords.ww_names),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])

        # Test Enable invalid word
        resp = self.bus.wait_for_response(Message("neon.enable_wake_word",
                                                  {"wake_word": "wake_up"}))
        self.assertIsInstance(resp, Message)
        self.assertEqual(resp.data, {"error": "ww not configured",
                                     "active": False,
                                     "wake_word": "wake_up"})
        self.assertEqual(set(self.service.hotwords.ww_names),
                         {'hey_neon', 'hey_mycroft'},
                         self.service.config['hotwords'])

    # TODO: Implement reload in Dinkum listener and re-implement test
    # def test_reload_hotwords(self):
    #     hotwords = self.service.hotwords.ww_names
    #     self.assertIsNotNone(hotwords)
    #     for spec in hotwords:
    #         engine = self.service.hotwords._plugins[spec].pop('engine')
    #         self.assertIsNotNone(engine)
    #         self.assertIsNone(self.service.loop.engines[spec].get('engine'))
    #         break
    #     mock_chunk = b'\xff' * 1024
    #     self.service.loop.responsive_recognizer.feed_hotwords(mock_chunk)
    #     while self.service.loop.needs_reload:
    #         sleep(0.5)
    #     for spec in hotwords.keys():
    #         self.assertIsNotNone(self.service.loop.engines[spec].get('engine'))


if __name__ == '__main__':
    unittest.main()
