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

from dataclasses import dataclass
from ovos_utils.log import LOG
from ovos_dinkum_listener.voice_loop.voice_loop import DinkumVoiceLoop


@dataclass
class NeonVoiceLoop(DinkumVoiceLoop):
    def _get_tx(self, stt_context):
        # handle lang detection from speech
        if "stt_lang" in stt_context:
            lang = self._validate_lang(stt_context["stt_lang"])
            stt_context["stt_lang"] = lang
            # note: self.stt.stream is recreated every listen start
            # this is safe to do, and makes lang be passed to self.execute
            self.stt.stream.language = lang
            if self.fallback_stt:
                self.fallback_stt.stream.language = lang

        # get text and trigger callback
        try:
            transcriptions = self.stt.stream_stop() or [""]
        except:
            LOG.exception("STT failed")
            transcriptions = [""]

        if not transcriptions and self.fallback_stt is not None:
            LOG.info("Attempting fallback STT plugin")
            transcriptions = self.fallback_stt.stream_stop() or [""]

        # TODO - some plugins return list of transcripts some just text
        # standardize support for this
        if isinstance(transcriptions, str):
            transcriptions = [transcriptions]
        stt_context["transcription"] = transcriptions
        return transcriptions, stt_context
