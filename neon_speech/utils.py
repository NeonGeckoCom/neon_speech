# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2025 Neongecko.com Inc.
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

from tempfile import mkstemp
from ovos_utils.log import LOG, deprecated
from neon_utils.packaging_utils import get_package_dependencies
from ovos_config.config import Configuration
from typing import List, Union


def patch_config(config: dict = None):
    """
    Write the specified speech configuration to the global config file
    :param config: Mycroft-compatible configuration override
    """
    from ovos_config.config import LocalConf
    from ovos_config.locations import USER_CONFIG
    LOG.warning(f"Patching configuration with: {config}")
    config = config or dict()
    local_config = LocalConf(USER_CONFIG)
    local_config.update(config)
    local_config.store()


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


def build_extra_dependency_list(config: Union[dict, Configuration], additional: List[str] = []) -> List[str]:
    extra_dependencies = config.get("extra_dependencies", {})
    dependencies = additional + extra_dependencies.get("global", []) + extra_dependencies.get("voice", [])

    return dependencies


@deprecated("Replaced by `neon_utils.packaging_utils.install_packages_from_pip`", "5.0.0")
def install_stt_plugin(plugin: str) -> bool:
    """
    Install an stt plugin using pip
    :param plugin: entrypoint of plugin to install
    :returns: True if the plugin installation is successful
    """
    import pip
    _, tmp_file = mkstemp()
    LOG.info(f"deps={get_package_dependencies('neon-speech')}")
    with open(tmp_file, 'w') as f:
        f.write('\n'.join(get_package_dependencies("neon-speech")))
    LOG.info(f"Requested installation of plugin: {plugin}")
    returned = pip.main(['install', _plugin_to_package(plugin), "-c",
                         tmp_file])
    LOG.info(f"pip status: {returned}")
    return returned == 0


def init_stt_plugin(plugin: str):
    """
    Initialize a specified plugin. Useful for doing one-time initialization
    before deployment
    """
    from ovos_plugin_manager.stt import load_stt_plugin
    plug = load_stt_plugin(plugin)
    if plug:
        LOG.info(f"Initializing plugin: {plugin}")
        try:
            plug()
        except TypeError:
            plug(results_event=None)
    else:
        LOG.warning(f"Could not find plugin: {plugin}")


@deprecated("Platform detection has been deprecated", "5.0.0")
def use_neon_speech(func):
    """
    Wrapper to ensure call originates from neon_speech for stack checks.
    This is used for ovos-utils config platform detection which uses the stack
    to determine which module config to return.
    """
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

