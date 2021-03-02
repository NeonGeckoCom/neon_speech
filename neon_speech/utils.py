import signal as sig
from ovos_utils.log import LOG
from ovos_utils.configuration import read_mycroft_config
import re
import pyaudio


def get_config():
    default = read_mycroft_config()
    return default or {
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
