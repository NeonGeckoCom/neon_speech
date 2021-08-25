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
from time import sleep

import os
import sys
import mock
import unittest

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
        while not cls.bus.started_running:
            sleep(1)
        alive = False
        while not alive:
            message = cls.bus.wait_for_response(Message("mycroft.speech.is_ready"))
            if message:
                alive = message.data.get("status")

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
                                                      context), context["ident"])
        self.assertEqual(stt_resp.context, context)
        self.assertIsInstance(stt_resp.data.get("parser_data"), dict)
        self.assertIsInstance(stt_resp.data.get("transcripts"), list)
        self.assertIn("stop", stt_resp.data.get("transcripts"))

    def test_audio_input_valid(self):
        handle_utterance = mock.Mock()
        self.bus.once("recognizer_loop:utterance", handle_utterance)
        context = {"client": "tester",
                   "ident": "11111",
                   "user": "TestRunner"}
        stt_resp = self.bus.wait_for_response(Message("neon.audio_input", {"audio_file": os.path.join(AUDIO_FILE_PATH,
                                                                                                      "stop.wav")},
                                                      context), context["ident"], 30.0)
        self.assertIsInstance(stt_resp, Message)
        for key in context:
            self.assertIn(key, stt_resp.context)
            self.assertEqual(context[key], stt_resp.context[key])
        self.assertIsInstance(stt_resp.data.get("skills_recv"), bool)
        handle_utterance.assert_called_once()

    # TODO: Test locking DM


if __name__ == '__main__':
    unittest.main()
