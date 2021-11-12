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

from typing import Optional
from abc import abstractmethod, ABCMeta, ABC
from inspect import signature
from multiprocessing import Queue
from threading import Event
from time import time
from neon_utils import LOG
from ovos_plugin_manager.templates.stt import STT as _STT, StreamThread, StreamingSTT
from ovos_plugin_manager.stt import load_stt_plugin, OVOSSTTFactory, get_stt_config
from mycroft_bus_client import MessageBusClient, Message
from speech_recognition import Recognizer
from neon_utils.configuration_utils import get_neon_speech_config


class STT(_STT, ABC):
    """ STT Base class, all  STT backends derives from this one. """
    def __init__(self, config=None):
        config_core = config or get_neon_speech_config()
        metric_upload = config_core.get("metric_upload", False)
        if metric_upload:
            server_addr = config_core.get("remote_server", "64.34.186.120")
            self.server_bus = MessageBusClient(host=server_addr)
            self.server_bus.run_in_thread()
        else:
            self.server_bus = None
        self.lang = str(self.init_language(config_core))
        config_stt = config_core.get("stt", {})
        module = config_stt.get("module", "")
        if "google_cloud" in module:
            module = "google_cloud"
        self.config = config_stt.get(module, {})
        self.credential = self.config.get("credential", {})
        self.recognizer = Recognizer()
        self.can_stream = False
        self.keys = config_core.get("keys", {})

    @staticmethod
    def init_language(config_core):
        lang = config_core.get("lang", "en-US")
        langs = lang.split("-")
        if len(langs) == 2:
            return langs[0].lower() + "-" + langs[1].upper()
        return lang




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
            config["module"] = "google" # TODO configurable fallback plugin
            clazz = OVOSSTTFactory.get_class(config)
            if not clazz:
                raise ValueError("fallback plugin not found")

        # TODO wrapped STT class like in TTS
        kwargs = {}
        params = signature(clazz).parameters
        if "results_event" in params:
            kwargs["results_event"] = results_event
        if "config" in params:
            kwargs["config"] = config
        return clazz(**kwargs)

