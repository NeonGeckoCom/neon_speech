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

from subprocess import Popen
from ovos_utils.configuration import read_mycroft_config
from neon_utils.configuration_utils import get_neon_speech_config
from neon_utils.lock_utils import create_lock
from neon_utils.logger import LOG


def get_config():
    mycroft = read_mycroft_config()
    neon = get_neon_speech_config()
    config = neon or mycroft
    return config or {
        "listener": {
            "sample_rate": 16000,
            "record_wake_words": False,
            "save_utterances": False,
            "mute_during_output": True,
            "duck_while_listening": 0.3,
            "phoneme_duration": 120,
            "multiplier": 1.0,
            "energy_ratio": 1.5,
            "stand_up_word": "wake up"
        }
    }


def _plugin_to_package(plugin: str) -> str:
    """
    Get a PyPI spec for a known plugin entrypoint
    :param plugin: plugin spec (i.e. config['stt']['module'])
    :returns: package name associated with `plugin` or `plugin`
    """
    known_plugins = {
        "deepspeech_stream_local": "neon-stt-plugin-deepspeech-stream-local",
        "polyglot": "neon-stt-plugin-polyglot",
        "google_cloud_streaming": "neon-stt-plugin-google-cloud-streaming",
    }
    return known_plugins.get(plugin) or plugin


def install_stt_plugin(plugin: str) -> bool:
    """
    Install an stt plugin using pip
    :param plugin: entrypoint of plugin to install
    :returns: True if the plugin installation is successful
    """
    LOG.info(f"Requested installation of plugin: {plugin}")
    # TODO: Translate plugin entrypoint to package
    can_pip = os.access(os.path.dirname(sys.executable), os.W_OK | os.X_OK)
    pip_cmd = [sys.executable, '-m', 'pip', 'install', plugin]
    if not can_pip:
        pip_cmd = ['sudo', '-n'] + pip_cmd
    with create_lock("stt_pip.lock"):
        proc = Popen(pip_cmd)
        code = proc.wait()
        if code != 0:
            error_trace = proc.stderr.read().decode()
            LOG.error(error_trace)
            return False
    return True
