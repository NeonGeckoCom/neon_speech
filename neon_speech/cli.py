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

import click

from click_default_group import DefaultGroup
from neon_utils.packaging_utils import get_package_version_spec
from neon_utils.configuration_utils import init_config_dir


@click.group("neon-speech", cls=DefaultGroup,
             no_args_is_help=True, invoke_without_command=True,
             help="Neon Core Commands\n\n"
                  "See also: neon COMMAND --help")
@click.option("--version", "-v", is_flag=True, required=False,
              help="Print the current version")
def neon_speech_cli(version: bool = False):
    if version:
        click.echo(f"neon_speech version "
                   f"{get_package_version_spec('neon_speech')}")


@neon_speech_cli.command(help="Start Neon Speech module")
@click.option("--module", "-m", default=None,
              help="STT Plugin to configure")
@click.option("--package", "-p", default=None,
              help="STT package spec to install")
@click.option("--force-install", "-f", default=False, is_flag=True,
              help="Force pip installation of configured module")
def run(module, package, force_install):
    init_config_dir()

    from neon_speech.__main__ import main
    from ovos_config.config import Configuration
    speech_config = Configuration()
    if force_install or module or package:
        install_plugin(module, package, force_install)
    if module and module != speech_config["stt"]["module"]:
        click.echo("Updating runtime config with module and package")
        package = package or speech_config["stt"].get("package_spec")
        speech_config["stt"]["module"] = module
        speech_config["stt"]["package_spec"] = package
        click.echo(f'Loading STT Module: {speech_config["stt"]["module"]}')
        click.echo(f'Speech Config={speech_config}')
        click.echo("Starting Speech Client")
        main(speech_config=speech_config, daemonic=True)
    else:
        click.echo("Starting Speech Client")
        main(daemonic=True)
    click.echo("Speech Client Shutdown")


@neon_speech_cli.command(help="Install an STT Plugin")
@click.option("--module", "-m", default=None,
              help="STT Plugin to configure")
@click.option("--package", "-p", default=None,
              help="STT package spec to install")
@click.option("--force-install", "-f", default=False, is_flag=True,
              help="Force pip installation of configured module")
def install_plugin(module, package, force_install):
    from neon_speech.utils import install_stt_plugin
    from ovos_config.config import Configuration
    speech_config = Configuration()

    if force_install and not (package or module):
        click.echo("Installing STT plugin from configuration")
        module = module or speech_config.get("stt", {}).get("module")
        package = package or speech_config.get("stt", {}).get("package_spec")

    if module:
        install_stt_plugin(package or module)
        if not module:
            click.echo("Plugin specified without module")


@neon_speech_cli.command(help="Install a STT Plugin")
@click.option("--plugin", "-p", default=None,
              help="STT module to init")
def init_plugin(plugin):
    from neon_speech.utils import init_stt_plugin
    from ovos_config.config import Configuration
    plugin = plugin or Configuration().get("stt", {}).get("module")
    init_stt_plugin(plugin)
