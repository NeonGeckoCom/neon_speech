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

from time import sleep, time
from multiprocessing import Process
from mycroft_bus_client import MessageBusClient, Message
from neon_utils.configuration_utils import get_neon_speech_config
from neon_utils.logger import LOG
from mycroft.messagebus.service.__main__ import main as messagebus_service

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from neon_speech.__main__ import main as neon_speech_main

AUDIO_FILE_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "audio_files")
TEST_CONFIG = get_neon_speech_config()
TEST_CONFIG["stt"]["module"] = "deepspeech_stream_local"


# TODO: Test non-streaming STT module DM
class TestAPIMethods(unittest.TestCase):
    bus_thread = None
    speech_thread = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bus_thread = Process(target=messagebus_service, daemon=False)
        cls.speech_thread = Process(target=neon_speech_main, kwargs={"speech_config": TEST_CONFIG}, daemon=False)
        cls.bus_thread.start()
        cls.speech_thread.start()
        cls.bus = MessageBusClient()
        cls.bus.run_in_thread()
        if not cls.bus.connected_event.wait(60):
            raise TimeoutError("Bus not connected after 60 seconds")
        alive = False
        timeout = time() + 120
        while not alive and time() < timeout:
            message = cls.bus.wait_for_response(
                Message("mycroft.speech.is_ready"))
            if message:
                alive = message.data.get("status")
        if not alive:
            raise TimeoutError("Speech module not ready after 120 seconds")

    @classmethod
    def tearDownClass(cls) -> None:
        super(TestAPIMethods, cls).tearDownClass()
        cls.bus_thread.terminate()
        cls.speech_thread.terminate()
        try:
            if cls.bus_thread.is_alive():
                LOG.error("Bus still alive")
                cls.bus_thread.kill()
            if cls.speech_thread.is_alive():
                LOG.error("Bus still alive")
                cls.speech_thread.kill()
        except Exception as e:
            LOG.error(e)

    def test_get_stt_no_file(self):
        context = {"client": "tester",
                   "ident": "123",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt", {}, context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)
        self.assertEqual(stt_resp.data["error"], "audio_file not specified!")

    def test_get_stt_invalid_file_path(self):
        context = {"client": "tester",
                   "ident": "1234",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt", {"audio_file": "~/invalid_file.wav"}, context),
                                              context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_invalid_file_type(self):
        context = {"client": "tester",
                   "ident": "123456",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                                                                  "test.txt")},
                                                      context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("error"), str)

    def test_get_stt_valid_file(self):
        context = {"client": "tester",
                   "ident": "12345",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.get_stt", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                                                                  "stop.wav")},
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
        stt_resp = self.bus.wait_for_response(Message("neon.audio_input", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                                                                      "stop.wav")},
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

    # TODO: Test locking DM


if __name__ == '__main__':
    unittest.main()
