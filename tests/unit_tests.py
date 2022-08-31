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
from neon_utils.logger import LOG
from speech_recognition import AudioData

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


class UtilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = os.path.join(dirname(__file__), "config")
        os.environ["NEON_CONFIG_PATH"] = config_path

    @classmethod
    def tearDownClass(cls) -> None:
        config_path = os.environ.pop("NEON_CONFIG_PATH")
        if os.path.exists(config_path):
            shutil.rmtree(config_path)

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
            "neon-stt-plugin-google_cloud_streaming>=0.2.7a0"))
        import neon_stt_plugin_google_cloud_streaming

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


if __name__ == '__main__':
    unittest.main()
