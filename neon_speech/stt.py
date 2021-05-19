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

import json
from abc import abstractmethod, ABCMeta, ABC
from inspect import signature
from multiprocessing import Queue
from threading import Event
from time import time

from ovos_utils.log import LOG
from ovos_plugin_manager.templates.stt import STT as _STT, StreamThread
from ovos_plugin_manager.stt import load_stt_plugin
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


class TokenSTT(STT, metaclass=ABCMeta):
    def __init__(self):
        super(TokenSTT, self).__init__()
        self.token = self.credential.get("token")


class GoogleJsonSTT(STT, metaclass=ABCMeta):
    def __init__(self):
        super(GoogleJsonSTT, self).__init__()
        if not self.credential.get("json") or self.keys.get("google_cloud"):
            self.credential["json"] = self.keys["google_cloud"]
        self.json_credentials = json.dumps(self.credential.get("json"))


class BasicSTT(STT, metaclass=ABCMeta):

    def __init__(self):
        super(BasicSTT, self).__init__()
        self.username = str(self.credential.get("username"))
        self.password = str(self.credential.get("password"))


class KeySTT(STT, metaclass=ABCMeta):

    def __init__(self):
        super(KeySTT, self).__init__()
        self.id = str(self.credential.get("client_id"))
        self.key = str(self.credential.get("client_key"))


class StreamingSTT(STT):
    """
        ABC class for threaded streaming STT implemenations.
    """

    def __init__(self, results_event, config=None):
        super().__init__(config)
        self.stream = None
        self.can_stream = True
        self.queue = None
        self.results_event = results_event

    def stream_start(self, language=None):
        self.stream_stop()
        self.queue = Queue()
        self.stream = self.create_streaming_thread()
        self.stream.start()

    def stream_data(self, data):
        self.queue.put(data)

    def stream_stop(self):
        if self.stream is not None:
            self.queue.put(None)
            self.stream.join()

            transcripts = self.stream.transcriptions

            self.stream = None
            self.queue = None
            return transcripts
        return None

    def execute(self, audio, language=None):
        if self.server_bus:
            start_time = time()
            transcripts = self.stream_stop()
            transcribe_time = time() - start_time
            stt_name = repr(self.__class__.__name__)
            print(f"{stt_name} | time={transcribe_time}")
            self.server_bus.emit(Message("neon.metric", {"name": "stt execute",
                                                         "transcripts": transcripts,
                                                         "time": transcribe_time,
                                                         "module": stt_name}))
            return transcripts
        else:
            return self.stream_stop()

    @abstractmethod
    def create_streaming_thread(self):
        pass


class STTFactory:
    CLASSES = {}

    @staticmethod
    def create(config=None, results_event: Event = None):
        if config and not config.get("module"):  # No module, try getting stt config from passed config
            config = config.get("stt")
        if not config:  # No config, go get it
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
