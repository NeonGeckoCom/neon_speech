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

from abc import ABC
from inspect import signature
from threading import Event

from neon_utils import LOG
from ovos_plugin_manager.stt import OVOSSTTFactory
from ovos_plugin_manager.templates.stt import STT, StreamThread
from ovos_plugin_manager.templates.stt import StreamingSTT as _Streaming

from ovos_config.config import Configuration


class StreamingSTT(_Streaming, ABC):
    def __init__(self, results_event=None, *_, **kwargs):
        super(StreamingSTT, self).__init__()
        if kwargs.get("config"):
            config = kwargs['config']
            self.config = config.get(config['module']) or self.config
        if results_event:
            # TODO: Deprecate this
            self.results_event = results_event
            self.transcript_ready = results_event

    def stream_stop(self):
        if self.stream is not None:
            self.queue.put(None)
            text = self.stream.finalize()
            to_return = [text]
            self.stream.join()
            if hasattr(self.stream, 'transcriptions'):
                to_return = self.stream.transcriptions
            self.stream = None
            self.queue = None
            self.transcript_ready.set()
            return to_return
        return None


class WrappedSTT:
    def __new__(cls, clazz, *args, **kwargs):
        # read config
        config_core = {'stt': kwargs.get("config")} or Configuration()
        # build STT
        for k in list(kwargs.keys()):
            if k not in signature(clazz).parameters:
                kwargs.pop(k)
        stt = clazz(*args, **kwargs)
        stt.keys = config_core.get("keys", {})
        return stt


class STTFactory(OVOSSTTFactory):
    @staticmethod
    def create(config=None, results_event: Event = None):
        if config and not config.get("module"):
            # No module, try getting stt config from passed config
            config = config.get("stt")
            LOG.info("Using passed config")
        if not config:  # No config, go get it
            config = Configuration().get("stt", {})
            from ovos_config.locations import USER_CONFIG
            LOG.info(f"Getting config from disk: {USER_CONFIG}")

        LOG.info(f"Create STT with config: {config}")
        clazz = OVOSSTTFactory.get_class(config)
        if not clazz:
            LOG.warning(f"{config.get('module')} plugin not found, "
                        f"falling back to Chromium STT")
            config["module"] = config.get("fallback_module") or "google"
            clazz = OVOSSTTFactory.get_class(config)
            if not clazz:
                raise ValueError("fallback plugin not found")

        return WrappedSTT(clazz, config=config, results_event=results_event)
