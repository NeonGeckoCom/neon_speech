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
from threading import Thread

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

    def test_install_stt_plugin(self):
        from neon_speech.utils import install_stt_plugin
        self.assertTrue(install_stt_plugin("neon-stt-plugin-google_cloud_streaming"))
        import neon_stt_plugin_google_cloud_streaming

    def test_patch_config(self):
        from neon_utils.configuration_utils import init_config_dir
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
        init_config_dir()

        from neon_speech.utils import patch_config
        test_config = {"new_key": {'val': True}}
        patch_config(test_config)
        conf_file = os.path.join(test_config_dir, 'neon',
                                 'neon.conf')
        self.assertTrue(os.path.isfile(conf_file))
        with open(conf_file) as f:
            config = json.load(f)

        self.assertTrue(config['new_key']['val'])
        shutil.rmtree(test_config_dir)
        os.environ.pop("XDG_CONFIG_HOME")

    def test_get_stt_from_file(self):
        from neon_speech.service import NeonSpeechClient
        from neon_messagebus.service import NeonBusService
        from mycroft.configuration import Configuration
        AUDIO_FILE_PATH = os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "audio_files")
        TEST_CONFIG = Configuration()
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
        bus.shutdown()
    # TODO: Test other speech service methods directly


if __name__ == '__main__':
    unittest.main()
