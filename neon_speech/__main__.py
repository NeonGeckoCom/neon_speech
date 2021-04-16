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
from mycroft_bus_client import MessageBusClient
from typing import Optional

import time

from threading import Lock

from ovos_utils import create_daemon, wait_for_exit_signal
from ovos_utils.messagebus import Message, get_mycroft_bus
from ovos_utils.log import LOG
from ovos_utils.json_helper import merge_dict
from pydub import AudioSegment
from speech_recognition import AudioData

from neon_speech.plugins import AudioParsersService
from neon_speech.utils import get_config
from neon_speech.listener import RecognizerLoop
from neon_speech.utils import reset_sigint_handler

bus: Optional[MessageBusClient] = None  # Mycroft messagebus connection
lock = Lock()
loop: Optional[RecognizerLoop] = None
config: Optional[dict] = None
service = None


def handle_record_begin():
    """Forward internal bus message to external bus."""
    LOG.info("Begin Recording...")
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('recognizer_loop:record_begin', context=context))


def handle_record_end():
    """Forward internal bus message to external bus."""
    LOG.info("End Recording...")
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('recognizer_loop:record_end', context=context))


def handle_no_internet():
    LOG.debug("Notifying enclosure of no internet connection")
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('enclosure.notify.no_internet', context=context))


def handle_awoken():
    """Forward mycroft.awoken to the messagebus."""
    LOG.info("Listener is now Awake: ")
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('mycroft.awoken', context=context))


def handle_utterance(event):
    LOG.info("Utterance: " + str(event['utterances']))
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'raw_audio': event.pop('raw_audio'),
               'destination': ["skills"],
               "timing": event.pop("timing", {})}
    if "data" in event:
        data = event.pop("data")
        context = merge_dict(context, data)
    if 'ident' in event:
        ident = event.pop('ident')
        context['ident'] = ident

    _emit_utterance_to_skills(Message('recognizer_loop:utterance', event, context))


def _emit_utterance_to_skills(message_to_emit: Message):
    """
    Emits a message containing a user utterance to skills for intent processing and checks that it is received by the
    skills module.
    """
    # Emit single intent request
    ident = message_to_emit.context['ident']
    resp = bus.wait_for_response(message_to_emit, timeout=10)
    if not resp:
        LOG.error(f"Skills didn't handle {ident}!")


def handle_wake_words_state(message):
    enabled = message.data.get("enabled", True)
    loop.change_wake_word_state(enabled)


def handle_hotword(event):
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    if not event.get("listen", False):
        LOG.info("Hotword Detected: " + event['hotword'])
        bus.emit(Message('recognizer_loop:hotword', event, context))
    else:
        LOG.info("Wakeword Detected: " + event['hotword'])
        bus.emit(Message('recognizer_loop:wakeword', event, context))


def handle_unknown():
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('mycroft.speech.recognition.unknown', context=context))


def handle_speak(event):
    """
        Forward speak message to message bus.
    """
    context = {'client_name': 'mycroft_listener',
               'source': 'audio',
               'destination': ["skills"]}
    bus.emit(Message('speak', event, context))


def handle_complete_intent_failure(message: Message):
    """Extreme backup for answering completely unhandled intent requests."""
    LOG.info("Failed to find intent.")
    # context = {'client_name': 'mycroft_listener',
    #            'source': 'audio',
    #            'destination': ["skills"]}
    bus.emit(message.forward("complete.intent.failure", message.data))


def handle_sleep(event):
    """Put the recognizer loop to sleep."""
    loop.sleep()


def handle_wake_up(event):
    """Wake up the the recognize loop."""
    loop.awaken()


def handle_mic_mute(event):
    """Mute the listener system."""
    loop.mute()


def handle_mic_unmute(event):
    """Unmute the listener system."""
    loop.unmute()


def handle_mic_listen(_):
    """Handler for mycroft.mic.listen.

    Starts listening as if wakeword was spoken.
    """
    loop.responsive_recognizer.trigger_listen()


def handle_mic_get_status(event):
    """Query microphone mute status."""
    data = {'muted': loop.is_muted()}
    message = event.response(data)
    message.context = {'client_name': 'mycroft_listener',
                       'source': 'audio',
                       'destination': ["skills"]}
    bus.emit(message)


def handle_audio_start(event):
    """Mute recognizer loop."""
    if config.get("listener").get("mute_during_output"):
        loop.mute()


def handle_audio_end(event):
    """Request unmute, if more sources have requested the mic to be muted
    it will remain muted.
    """
    if config.get("listener").get("mute_during_output"):
        loop.unmute()  # restore


def handle_stop(event):
    """Handler for mycroft.stop, i.e. button press."""
    loop.force_unmute()


def handle_input_from_klat(message):
    """
    Handles an input from the klat server
    """
    audio_file = message.data.get("raw_audio")
    nick = message.data.get("user")
    loop.consumer.chat_user_database.update_profile_for_nick(nick)
    chat_user = loop.consumer.chat_user_database.get_profile(nick)
    stt_language = chat_user["speech"].get('stt_language', 'en')
    request_id = f"sid-{message.data.get('sid')}-{message.data.get('socketIdEncrypted')}-" \
                 f"{nick}-{message.data.get('nano')}"  # Formerly known as 'flac_filename'

    try:
        nick_profiles = loop.consumer.chat_user_database.get_nick_profiles(message.data.get("cid_nicks"))
    except TypeError:
        nick_profiles = loop.consumer.chat_user_database.get_nick_profiles([nick])
    mobile = message.data.get("nano") == "mobile"
    if mobile:
        client = "mobile"
    elif message.data.get("nano") == "true":
        client = "nano"
    else:
        client = "klat"
    ident = time.time()

    LOG.debug(audio_file)
    if audio_file:
        try:
            segment = AudioSegment.from_file(audio_file)
            audio_data = AudioData(segment.raw_data, segment.frame_rate, segment.sample_width)
            LOG.debug("Got audio_data")
            audio, audio_context = loop.responsive_recognizer.audio_consumers.get_context(audio_data)
            LOG.debug(f"Got context: {audio_context}")
            audio_context["user"] = nick

            if message.data.get("need_transcription"):
                transcriptions = loop.consumer.transcribe(audio, audio_context)  # flac_data for Google Beta STT
                LOG.debug(f"return stt to server: {transcriptions}")
                bus.emit(Message("css.emit", {"event": "stt from mycroft",
                                              "data": [transcriptions[0], request_id]}))
            else:
                transcriptions = [message.data.get("shout_text")]
        except Exception as x:
            LOG.error(x)
            transcriptions = [message.data.get("shout_text")]
            audio_context = None
    elif message.data.get("need_transcription"):
        LOG.error(f"Need transcription but no audio passed! {message}")
        return
    else:
        audio_context = None
        transcriptions = [message.data.get("shout_text")]

    if not transcriptions:
        LOG.warning(f"Null Transcription!")
        return

    data = {
        "utterances": transcriptions,
        "lang": stt_language
    }
    context = {'client_name': 'mycroft_listener',
               'source': 'klat',
               'destination': ["skills"],
               "audio_parser_data": audio_context,
               "raw_audio": message.data.get("raw_audio"),
               "mobile": mobile,  # TODO: Depreciate and use client DM
               "client": client,  # origin (local, klat, nano, mobile, api)
               "klat_data": {"cid": message.data.get("cid"),
                             "sid": message.data.get("sid"),
                             "title": message.data.get("title"),
                             "nano": message.data.get("nano"),
                             "request_id": request_id},
               # "flac_filename": flac_filename,
               "neon_should_respond": False,
               "username": nick,
               "nick_profiles": nick_profiles,
               "cc_data": {"speak_execute": transcriptions[0],
                           "raw_utterance": transcriptions[0]},  # TODO: Are these necessary anymore? Shouldn't be DM
               "timing": {"start": message.data.get("time"),
                          "transcribed": time.time()},
               "ident": ident
               }
    LOG.debug("Send server request to skills for processing")
    _emit_utterance_to_skills(Message('recognizer_loop:utterance', data, context))


def main():
    global bus
    global loop
    global config
    global service
    reset_sigint_handler()
    bus = get_mycroft_bus()  # Mycroft messagebus, see mycroft.messagebus
    config = get_config()

    # Register handlers on internal RecognizerLoop emitter
    loop = RecognizerLoop(config)
    loop.on('recognizer_loop:utterance', handle_utterance)
    loop.on('recognizer_loop:speech.recognition.unknown', handle_unknown)
    loop.on('speak', handle_speak)
    loop.on('recognizer_loop:record_begin', handle_record_begin)
    loop.on('recognizer_loop:awoken', handle_awoken)
    loop.on('recognizer_loop:hotword', handle_hotword)
    loop.on('recognizer_loop:record_end', handle_record_end)
    loop.on('recognizer_loop:no_internet', handle_no_internet)

    # Register handlers for events on main Mycroft messagebus
    bus.on('complete_intent_failure', handle_complete_intent_failure)
    bus.on('recognizer_loop:sleep', handle_sleep)
    bus.on('recognizer_loop:wake_up', handle_wake_up)
    bus.on('mycroft.mic.mute', handle_mic_mute)
    bus.on('mycroft.mic.unmute', handle_mic_unmute)
    bus.on('mycroft.mic.get_status', handle_mic_get_status)
    bus.on('mycroft.mic.listen', handle_mic_listen)
    bus.on('recognizer_loop:audio_output_start', handle_audio_start)
    bus.on('recognizer_loop:audio_output_end', handle_audio_end)
    bus.on('mycroft.stop', handle_stop)

    bus.on('recognizer_loop:klat_utterance', handle_input_from_klat)

    bus.on("neon.wake_words_state", handle_wake_words_state)

    service = AudioParsersService(bus, config=config)
    service.start()
    loop.bind(service)

    create_daemon(loop.run)

    wait_for_exit_signal()


if __name__ == "__main__":
    main()
