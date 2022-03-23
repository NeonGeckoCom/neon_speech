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
from inspect import signature
from threading import Event

from mycroft_bus_client import MessageBusClient
from neon_utils import LOG
from neon_utils.configuration_utils import get_neon_speech_config
from ovos_plugin_manager.stt import OVOSSTTFactory
from ovos_plugin_manager.templates.stt import STT, StreamingSTT


class WrappedSTT:
    def __new__(cls, clazz, *args, **kwargs):
        # read config
        config_core = kwargs.get("config") or get_neon_speech_config()
        metric_upload = config_core.get("metric_upload", False)
        # build STT
        for k in list(kwargs.keys()):
            if k not in signature(clazz).parameters:
                kwargs.pop(k)
        stt = clazz(*args, **kwargs)
        # add missing properties
        if metric_upload:
            server_addr = config_core.get("remote_server", "64.34.186.120")
            stt.server_bus = MessageBusClient(host=server_addr)
            stt.server_bus.run_in_thread()
        else:
            stt.server_bus = None
        stt.keys = config_core.get("keys", {})
        return stt


class STTFactory(OVOSSTTFactory):
    @staticmethod
    def create(config=None, results_event: Event = None):
        if config and not config.get("module"):  # No module, try getting stt config from passed config
            config = config.get("stt")
        if not config:  # No config, go get it
            config = get_neon_speech_config().get("stt", {})

        clazz = OVOSSTTFactory.get_class(config)
        if not clazz:
            LOG.warning("plugin not found, falling back to Chromium STT")
            config["module"] = "google"  # TODO configurable fallback plugin
            clazz = OVOSSTTFactory.get_class(config)
            if not clazz:
                raise ValueError("fallback plugin not found")

        return WrappedSTT(clazz, config=config, results_event=results_event)
