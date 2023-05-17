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
import sys
import mock
import unittest

from threading import Event
from time import time
from ovos_bus_client import Message
from neon_utils.configuration_utils import init_config_dir
from neon_utils.file_utils import encode_file_to_base64_string
from ovos_utils.messagebus import FakeBus
from ovos_utils.log import LOG
from ovos_config.config import Configuration, update_mycroft_config

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from neon_speech.service import NeonSpeechClient
from neon_speech.utils import use_neon_speech

AUDIO_FILE_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                               "audio_files")


class TestAPIMethodsStreaming(unittest.TestCase):
    speech_thread = None
    bus = FakeBus()
    bus.connected_event = Event()
    bus.connected_event.set()

    @classmethod
    def setUpClass(cls) -> None:
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
        use_neon_speech(init_config_dir)()
        update_mycroft_config({"stt": {"module": "deepspeech_stream_local"}})
        test_config = Configuration()
        assert test_config["stt"]["module"] == "deepspeech_stream_local"

        cls.speech_service = NeonSpeechClient(speech_config=test_config,
                                              daemonic=False, bus=cls.bus)
        cls.speech_service.start()
        ready = False
        timeout = time() + 120
        while not ready and time() < timeout:
            message = cls.bus.wait_for_response(
                Message("mycroft.speech.is_ready"))
            if message:
                ready = message.data.get("status")
        if not ready:
            raise TimeoutError("Speech module not ready after 120 seconds")

    @classmethod
    def tearDownClass(cls) -> None:
        super(TestAPIMethodsStreaming, cls).tearDownClass()
        try:
            cls.speech_service.shutdown()
        except Exception as e:
            LOG.error(e)

    def test_get_stt_no_file(self):
        context = {"client": "tester",
                   "ident": "123",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt",
                                                      {}, context),
                                              context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)
        self.assertEqual(stt_resp.data["error"], "audio_file not specified!")

    def test_get_stt_invalid_file_path(self):
        context = {"client": "tester",
                   "ident": "1234",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(
            Message("neon.get_stt", {"audio_file": "~/invalid_file.wav"},
                    context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_invalid_file_type(self):
        context = {"client": "tester",
                   "ident": "123456",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(
            Message("neon.get_stt",
                    {"audio_file": os.path.join(AUDIO_FILE_PATH, "test.txt")},
                    context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_valid_file(self):
        context = {"client": "tester",
                   "ident": "12345",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message(
            "neon.get_stt", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                        "stop.wav")},
            context), context["ident"], 60.0)
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("parser_data"), dict,
                              stt_resp.serialize())
        self.assertIsInstance(stt_resp.data.get("transcripts"), list,
                              stt_resp.serialize())
        self.assertIn("stop", stt_resp.data.get("transcripts"))

    def test_get_stt_valid_contents(self):
        context = {"client": "tester",
                   "ident": "12345",
                   "user": "TestRunner"}
        audio_data = encode_file_to_base64_string(os.path.join(AUDIO_FILE_PATH,
                                                               "stop.wav"))
        stt_resp = self.bus.wait_for_response(Message(
            "neon.get_stt", {"audio_data": audio_data},
            context), context["ident"], 60.0)
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("parser_data"), dict,
                              stt_resp.serialize())
        self.assertIsInstance(stt_resp.data.get("transcripts"), list,
                              stt_resp.serialize())
        self.assertIn("stop", stt_resp.data.get("transcripts"))

    def test_audio_input_valid(self):
        handle_utterance = mock.Mock()
        self.bus.once("recognizer_loop:utterance", handle_utterance)
        context = {"client": "tester",
                   "ident": "11111",
                   "user": "TestRunner",
                   "extra_data": "something"}
        audio_data = encode_file_to_base64_string(os.path.join(AUDIO_FILE_PATH,
                                                               "stop.wav"))
        stt_resp = self.bus.wait_for_response(Message(
            "neon.audio_input", {"audio_data": audio_data},
            context), context["ident"], 60.0)
        self.assertIsInstance(stt_resp, Message)
        for key in context:
            self.assertIn(key, stt_resp.context)
            self.assertEqual(context[key], stt_resp.context[key])
        self.assertIsInstance(stt_resp.data.get("skills_recv"), bool,
                              stt_resp.serialize())

        handle_utterance.assert_called_once()
        message = handle_utterance.call_args[0][0]
        self.assertIsInstance(message, Message)
        for key in context:
            self.assertIn(key, message.context)
            self.assertEqual(context[key], message.context[key])
        self.assertIsInstance(message.data["utterances"], list, message.data)
        self.assertIn("stop", message.data["utterances"],
                      message.data.get("utterances"))
        self.assertIsInstance(message.context["timing"], dict)
        self.assertEqual(message.context["destination"], ["skills"])

    def test_wake_words_state(self):
        self.bus.emit(Message("neon.wake_words_state", {"enabled": True}))
        resp = self.bus.wait_for_response(Message(
            "neon.query_wake_words_state"))
        self.assertTrue(resp.data['enabled'])
        self.bus.emit(Message("neon.wake_words_state", {"enabled": False}))
        resp = self.bus.wait_for_response(Message(
            "neon.query_wake_words_state"))
        self.assertFalse(resp.data['enabled'])

    def test_get_stt_supported_languages(self):
        real_stt = self.speech_service.loop.stt
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.stt", {}, {'ctx': True}
        ))
        self.assertIsInstance(resp, Message)
        self.assertTrue(resp.context.get('ctx'))

        self.assertEqual(resp.data['langs'],
                         list(real_stt.available_languages) or ['en-us'])

        mock_languages = ('en-us', 'es', 'fr-fr', 'fr-ca')
        from ovos_plugin_manager.templates.stt import STT

        class MockSTT(STT):
            def __init__(self):
                super(MockSTT, self).__init__()

            @property
            def available_languages(self):
                return mock_languages

            def execute(self, *args, **kwargs):
                pass

        mock_stt = MockSTT()
        self.speech_service.loop.stt = mock_stt
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.stt", {}, {'ctx': True}
        ))
        self.assertEqual(resp.data['langs'], list(mock_languages))

        self.speech_service.loop.stt = real_stt


class TestAPIMethodsNonStreaming(unittest.TestCase):
    speech_thread = None
    bus = FakeBus()
    bus.connected_event = Event()
    bus.connected_event.set()

    @classmethod
    def setUpClass(cls) -> None:
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
        use_neon_speech(init_config_dir)()

        test_config = Configuration()
        test_config["stt"]["module"] = "neon-stt-plugin-nemo"
        assert test_config["stt"]["module"] == "neon-stt-plugin-nemo"

        cls.speech_service = NeonSpeechClient(speech_config=test_config,
                                              daemonic=False, bus=cls.bus)
        cls.speech_service.start()
        ready = False
        timeout = time() + 120
        while not ready and time() < timeout:
            message = cls.bus.wait_for_response(
                Message("mycroft.speech.is_ready"))
            if message:
                ready = message.data.get("status")
        if not ready:
            raise TimeoutError("Speech module not ready after 120 seconds")

    @classmethod
    def tearDownClass(cls) -> None:
        super(TestAPIMethodsNonStreaming, cls).tearDownClass()
        try:
            cls.speech_service.shutdown()
        except Exception as e:
            LOG.error(e)

    def test_get_stt_no_file(self):
        context = {"client": "tester",
                   "ident": "123",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt",
                                                      {}, context),
                                              context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)
        self.assertEqual(stt_resp.data["error"], "audio_file not specified!")

    def test_get_stt_invalid_file_path(self):
        context = {"client": "tester",
                   "ident": "1234",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(
            Message("neon.get_stt", {"audio_file": "~/invalid_file.wav"},
                    context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_invalid_file_type(self):
        context = {"client": "tester",
                   "ident": "123456",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(
            Message("neon.get_stt",
                    {"audio_file": os.path.join(AUDIO_FILE_PATH, "test.txt")},
                    context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_valid_file(self):
        context = {"client": "tester",
                   "ident": "12345",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message(
            "neon.get_stt", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                        "stop.wav")},
            context), context["ident"], 60.0)
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("parser_data"), dict,
                              stt_resp.serialize())
        self.assertIsInstance(stt_resp.data.get("transcripts"), list,
                              stt_resp.serialize())
        self.assertIn("stop", stt_resp.data.get("transcripts"))

    def test_get_stt_valid_contents(self):
        context = {"client": "tester",
                   "ident": "12345",
                   "user": "TestRunner"}
        audio_data = encode_file_to_base64_string(os.path.join(AUDIO_FILE_PATH,
                                                               "stop.wav"))
        stt_resp = self.bus.wait_for_response(Message(
            "neon.get_stt", {"audio_data": audio_data},
            context), context["ident"], 60.0)
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("parser_data"), dict,
                              stt_resp.serialize())
        self.assertIsInstance(stt_resp.data.get("transcripts"), list,
                              stt_resp.serialize())
        self.assertIn("stop", stt_resp.data.get("transcripts"))

    def test_audio_input_valid(self):
        handle_utterance = mock.Mock()
        self.bus.once("recognizer_loop:utterance", handle_utterance)
        context = {"client": "tester",
                   "ident": "11111",
                   "user": "TestRunner",
                   "extra_data": "something"}
        audio_data = encode_file_to_base64_string(os.path.join(AUDIO_FILE_PATH,
                                                               "stop.wav"))
        stt_resp = self.bus.wait_for_response(Message(
            "neon.audio_input", {"audio_data": audio_data},
            context), context["ident"], 60.0)
        self.assertIsInstance(stt_resp, Message)
        for key in context:
            self.assertIn(key, stt_resp.context)
            self.assertEqual(context[key], stt_resp.context[key])
        self.assertIsInstance(stt_resp.data.get("skills_recv"), bool,
                              stt_resp.serialize())

        handle_utterance.assert_called_once()
        message = handle_utterance.call_args[0][0]
        self.assertIsInstance(message, Message)
        for key in context:
            self.assertIn(key, message.context)
            self.assertEqual(context[key], message.context[key])
        self.assertIsInstance(message.data["utterances"], list, message.data)
        self.assertIn("stop", message.data["utterances"],
                      message.data.get("utterances"))
        self.assertIsInstance(message.context["timing"], dict)
        self.assertEqual(message.context["destination"], ["skills"])

    def test_wake_words_state(self):
        self.bus.emit(Message("neon.wake_words_state", {"enabled": True}))
        resp = self.bus.wait_for_response(Message(
            "neon.query_wake_words_state"))
        self.assertTrue(resp.data['enabled'])
        self.bus.emit(Message("neon.wake_words_state", {"enabled": False}))
        resp = self.bus.wait_for_response(Message(
            "neon.query_wake_words_state"))
        self.assertFalse(resp.data['enabled'])

    def test_get_stt_supported_languages(self):
        from ovos_plugin_manager.templates.stt import STT

        real_stt = self.speech_service.loop.stt
        self.assertIsInstance(real_stt, STT)
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.stt", {}, {'ctx': True}
        ))
        self.assertIsInstance(resp, Message)
        self.assertTrue(resp.context.get('ctx'))

        self.assertEqual(resp.data['langs'],
                         list(real_stt.available_languages) or ['en-us'])

        mock_languages = ('en-us', 'es', 'fr-fr', 'fr-ca')

        class MockSTT(STT):
            def __init__(self):
                super(MockSTT, self).__init__()

            @property
            def available_languages(self):
                return mock_languages

            def execute(self, *args, **kwargs):
                pass

        mock_stt = MockSTT()
        self.speech_service.loop.stt = mock_stt
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.stt", {}, {'ctx': True}
        ))
        self.assertEqual(resp.data['langs'], list(mock_languages))

        self.speech_service.loop.stt = real_stt


if __name__ == '__main__':
    unittest.main()
