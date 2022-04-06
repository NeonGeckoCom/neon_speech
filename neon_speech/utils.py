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

from os.path import join
from tempfile import mkstemp
from ovos_utils.configuration import get_ovos_config
from ovos_utils.xdg_utils import xdg_config_home
from neon_utils.configuration_utils import get_neon_speech_config
from neon_utils.logger import LOG
from neon_utils.packaging_utils import get_package_dependencies


def get_speech_module_config() -> dict:
    """
    Get a dict config with all values required for the speech module read from
    Neon YML config
    :returns: dict Mycroft config with Neon YML values where defined
    """
    ovos = get_ovos_config()
    if "hotwords" in ovos:
        conf = ovos.pop("hotwords")
        LOG.debug(f"removed hostwords config: {conf}")
    neon = get_neon_speech_config()
    return {**ovos, **neon}


def patch_config(config: dict = None):
    """
    Write the specified speech configuration to the global config file
    :param config: Mycroft-compatible configuration override
    """
    config = config or dict()
    updated_config = {**get_speech_module_config(), **config}
    config_path = join(xdg_config_home(), "neon", "neon.conf")
    with open(config_path, "w+") as f:
        json.dump(updated_config, f)
    LOG.info(f"Updated config file: {config_path}")


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
    import pip
    _, tmp_file = mkstemp()
    with open(tmp_file, 'w') as f:
        f.write('\n'.join(get_package_dependencies("neon-speech")))
    LOG.info(f"Requested installation of plugin: {plugin}")
    returned = pip.main(['install', _plugin_to_package(plugin), "-c", tmp_file])
    LOG.info(f"pip status: {returned}")
    return returned == 0
