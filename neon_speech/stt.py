# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending
#
# This software is an enhanced derivation of the Mycroft Project which is licensed under the
# Apache software Foundation software license 2.0 https://www.apache.org/licenses/LICENSE-2.0
# Changes Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from inspect import signature
from threading import Event
from ovos_utils.log import LOG
from ovos_utils.plugins.stt import GoogleJsonSTT, StreamingSTT, StreamThread
# from ovos_plugin_manager.stt import load_stt_plugin
from ovos_utils.plugins import load_plugin
from neon_utils.configuration_utils import get_neon_speech_config
# from neon_speech.plugins import load_plugin


def load_stt_plugin(module_name):
    """Wrapper function for loading stt plugin.

    Arguments:
        (str) Mycroft stt module name from config
    """
    return load_plugin('mycroft.plugin.stt', module_name)


class STTFactory:
    CLASSES = {
        # "google_cloud": GoogleCloudSTT,
        # "google_cloud_streaming": GoogleCloudStreamingSTT
    }

    @staticmethod
    def create(config=None, results_event: Event = None):
        if not config:
            config = get_neon_speech_config().get("stt", {})
        # config = config or {}
        module = config.get("module", "chromium_stt_plug")

        try:
            if module in STTFactory.CLASSES:
                clazz = STTFactory.CLASSES[module]
            else:
                clazz = load_stt_plugin(module)
                LOG.info('Loaded the STT plugin {}'.format(module))

            kwargs = {}
            params = signature(clazz).parameters
            if "results_event" in params:
                kwargs["results_event"] = results_event
            if "config" in params:
                kwargs["config"] = config
            return clazz(**kwargs)
        except Exception as e:
            # The STT backend failed to start. Report it and fall back to
            # default.
            LOG.error(e)
            LOG.exception('The selected STT backend could not be loaded, '
                          'falling back to default...')
            if module != 'chromium_stt_plug':
                clazz = load_stt_plugin("chromium_stt_plug")
                LOG.info('Loaded fallback STT plugin {}'.format(module))
                return clazz()
            else:
                raise
