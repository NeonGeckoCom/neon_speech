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
from ovos_plugin_manager.stt import OVOSSTTFactory, get_stt_config
from ovos_plugin_manager.templates.stt import STT, StreamThread, StreamingSTT

from ovos_config.config import Configuration


class WrappedSTT(StreamingSTT, ABC):
    def __new__(cls, base_engine, *args, **kwargs):
        results_event = kwargs.get("results_event") or Event()
        # build STT
        for k in list(kwargs.keys()):
            if k not in signature(base_engine).parameters:
                kwargs.pop(k)
        base_engine.stream_stop = cls.stream_stop
        stt = base_engine(*args, **kwargs)
        stt.results_event = results_event
        stt.keys = Configuration().get("keys", {})
        return stt

    def stream_stop(self):
        if self.stream is not None:
            self.queue.put(None)
            text = self.stream.finalize()
            self.stream.join()
            if not hasattr(self.stream, 'transcriptions'):
                self.stream.transcriptions = [text]
            to_return = self.stream.transcriptions
            self.stream = None
            self.queue = None
            self.results_event.set()
            return to_return
        return None


class STTFactory(OVOSSTTFactory):
    @staticmethod
    def create(config=None, results_event: Event = None):
        get_stt_config(config)
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
        if issubclass(clazz, StreamingSTT):
            return WrappedSTT(clazz, config=config.get(config['module']),
                              results_event=results_event)
        else:
            return clazz(config=config.get(config['module']))
