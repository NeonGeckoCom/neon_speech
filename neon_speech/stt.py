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
from queue import Queue
from ovos_utils.log import LOG
from ovos_utils.plugins.stt import GoogleJsonSTT, StreamingSTT, StreamThread
from neon_utils.configuration_utils import NGIConfig
from neon_speech.plugins import load_plugin


# TODO make plugins for these and remove from here
class GoogleStreamThread(StreamThread):
    def __init__(self, queue, lang, client, streaming_config):
        super().__init__(queue, lang)
        self.client = client
        self.streaming_config = streaming_config

    def handle_audio_stream(self, audio, language):
        req = (types.StreamingRecognizeRequest(audio_content=x) for x in audio)
        responses = self.client.streaming_recognize(self.streaming_config, req)
        for res in responses:
            if res.results and res.results[0].is_final:
                self.text = res.results[0].alternatives[0].transcript
        return self.text


class GoogleCloudStreamingSTT(StreamingSTT):
    """
        Streaming STT interface for Google Cloud Speech-To-Text
        To use pip install google-cloud-speech and add the
        Google API key to local mycroft.conf file. The STT config
        will look like this:

        "stt": {
            "module": "google_cloud_streaming",
            "google_cloud_streaming": {
                "credential": {
                    "json": {
                        # Paste Google API JSON here
        ...

    """

    def __init__(self):
        global SpeechClient, types, enums, Credentials
        from google.cloud.speech import SpeechClient, types, enums
        from google.oauth2.service_account import Credentials

        super(GoogleCloudStreamingSTT, self).__init__()
        # override language with module specific language selection
        self.language = self.config.get('lang') or self.lang

        if not self.credential.get("json") or self.keys.get("google_cloud"):
            self.credential["json"] = self.keys["google_cloud"]

        credentials = Credentials.from_service_account_info(
            self.credential.get('json')
        )

        self.client = SpeechClient(credentials=credentials)
        recognition_config = types.RecognitionConfig(
            encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=self.language,
            model='command_and_search',
            max_alternatives=1,
        )
        self.streaming_config = types.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True,
            single_utterance=True,
        )

    def create_streaming_thread(self):
        self.queue = Queue()
        return GoogleStreamThread(
            self.queue,
            self.language,
            self.client,
            self.streaming_config
        )


class GoogleCloudSTT(GoogleJsonSTT):
    def __init__(self):
        super(GoogleCloudSTT, self).__init__()
        # override language with module specific language selection
        self.lang = self.config.get('lang') or self.lang

    def execute(self, audio, language=None):
        self.lang = language or self.lang
        return self.recognizer.recognize_google_cloud(audio,
                                                      self.json_credentials,
                                                      self.lang)


def load_stt_plugin(module_name):
    """Wrapper function for loading stt plugin.

    Arguments:
        (str) Mycroft stt module name from config
    """
    return load_plugin('mycroft.plugin.stt', module_name)


class STTFactory:
    CLASSES = {
        "google_cloud": GoogleCloudSTT,
        "google_cloud_streaming": GoogleCloudStreamingSTT
    }

    @staticmethod
    def create(config=None):
        try:
            if not config:
                config = NGIConfig("ngi_user_info").content.get("stt", {})
            # config = config or {}
            module = config.get("module", "chromium_stt_plug")
            if module in STTFactory.CLASSES:
                clazz = STTFactory.CLASSES[module]
            else:
                clazz = load_stt_plugin(module)
                LOG.info('Loaded the STT plugin {}'.format(module))
            return clazz()
        except Exception as e:
            # The STT backend failed to start. Report it and fall back to
            # default.
            LOG.exception('The selected STT backend could not be loaded, '
                          'falling back to default...')
            if module != 'chromium_stt_plug':
                clazz = load_stt_plugin("chromium_stt_plug")
                LOG.info('Loaded fallback STT plugin {}'.format(module))
                return clazz()
            else:
                raise
