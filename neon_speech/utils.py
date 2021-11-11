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

import re
import pyaudio
import signal as sig

from neon_utils import LOG
from ovos_utils.configuration import read_mycroft_config
from neon_utils.configuration_utils import get_neon_speech_config


def get_config():
    mycroft = read_mycroft_config()
    neon = get_neon_speech_config()
    config = neon or mycroft
    return config or {
        "listener": {
            "sample_rate": 16000,
            "record_wake_words": False,
            "save_utterances": False,
            "mute_during_output": True,
            "duck_while_listening": 0.3,
            "phoneme_duration": 120,
            "multiplier": 1.0,
            "energy_ratio": 1.5,
            "stand_up_word": "wake up"
        }
    }


def reset_sigint_handler():
    """
    Reset the sigint handler to the default. This fixes KeyboardInterrupt
    not getting raised when started via start-mycroft.sh
    """
    sig.signal(sig.SIGINT, sig.default_int_handler)


def find_input_device(device_name):
    """ Find audio input device by name.

        Arguments:
            device_name: device name or regex pattern to match

        Returns: device_index (int) or None if device wasn't found
    """
    LOG.info('Searching for input device: {}'.format(device_name))
    LOG.debug('Devices: ')
    pa = pyaudio.PyAudio()
    pattern = re.compile(device_name)
    for device_index in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(device_index)
        LOG.debug('   {}'.format(dev['name']))
        if dev['maxInputChannels'] > 0 and pattern.match(dev['name']):
            LOG.debug('    ^-- matched')
            return device_index
    return None
