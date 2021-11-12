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

from ovos_plugin_manager.audio_transformers import find_audio_transformer_plugins
from ovos_utils.json_helper import merge_dict
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
# USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
from ovos_utils.log import LOG
from speech_recognition import AudioData


class AudioTransformersService:

    def __init__(self, bus, config=None):
        self.config_core = config or {}
        self.loaded_modules = {}
        self.has_loaded = False
        self.bus = bus
        self.config = self.config_core.get("audio_transformers") or {"neon_noise_level_plugin": {}}
        self.load_plugins()

    def load_plugins(self):
        for plug_name, plug in find_audio_transformer_plugins().items():
            if plug_name in self.config:
                # if disabled skip it
                if not self.config[plug_name].get("active", True):
                    continue
                try:
                    self.loaded_modules[plug_name] = plug()
                    LOG.info(f"loaded audio transfomer plugin: {plug_name}")
                except Exception as e:
                    LOG.exception(f"Failed to load audio transfomer plugin: {plug_name}")

    @property
    def modules(self):
        return self.loaded_modules.values()

    def shutdown(self):
        pass

    def get_chunk(self, audio_data):
        if isinstance(audio_data, AudioData):
            chunk = audio_data.frame_data
            for module in self.modules:
                module.sample_rate = audio_data.sample_rate
                module.sample_width = audio_data.sample_width
        else:
            chunk = audio_data
        return chunk

    def feed_audio(self, audio_data):
        chunk = self.get_chunk(audio_data)
        for module in self.modules:
            module.feed_audio_chunk(chunk)

    def feed_hotword(self, audio_data):
        chunk = self.get_chunk(audio_data)
        for module in self.modules:
            module.feed_hotword_chunk(chunk)

    def feed_speech(self, audio_data):
        chunk = self.get_chunk(audio_data)
        for module in self.modules:
            module.feed_speech_chunk(chunk)

    def get_context(self, audio_data):
        context = {}
        chunk = self.get_chunk(audio_data)
        for module in self.modules:
            chunk, data = module.feed_speech_utterance(chunk)
            LOG.debug(f"{module.name}: {data}")
            context = merge_dict(context, data)
            # core expects a AudioData object
            audio_data.frame_data = chunk
        return audio_data, context
