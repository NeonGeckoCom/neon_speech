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

from os.path import dirname
from neon_utils.configuration_utils import get_neon_local_config
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

    def test_get_speech_module_config(self):
        from neon_speech.utils import get_speech_module_config
        config = get_speech_module_config()
        self.assertIsInstance(config, dict)
        self.assertIsInstance(config["stt"], dict)
        self.assertIsInstance(config["listener"], dict)
        local_config = get_neon_local_config()
        local_config["stt"]["module"] = "test_mod"
        local_config.write_changes()
        new_config = get_speech_module_config()
        self.assertNotEqual(config, new_config)
        self.assertEqual(new_config["stt"]["module"], "test_mod")

    def test_install_stt_plugin(self):
        from neon_speech.utils import install_stt_plugin
        self.assertTrue(install_stt_plugin("neon-stt-plugin-polyglot"))
        import neon_stt_plugin_polyglot

    def test_patch_config(self):
        from neon_speech.utils import patch_config
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
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


if __name__ == '__main__':
    unittest.main()
