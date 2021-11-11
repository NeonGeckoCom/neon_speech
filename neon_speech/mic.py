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

import datetime
import os
import pyaudio
import speech_recognition
import audioop

from typing import Optional
from time import sleep, time as get_time
from collections import deque
from os.path import isdir, join
from hashlib import md5

from phoneme_guesser import FailedToGuessPhonemes
from speech_recognition import AudioSource, AudioData
from tempfile import gettempdir
from ovos_utils import resolve_resource_file
from ovos_utils.signal import check_for_signal, get_ipc_directory
from ovos_utils.sound import play_ogg, play_wav, play_mp3
from neon_utils import LOG
from ovos_utils.lang.phonemes import get_phonemes
from neon_utils.file_utils import resolve_neon_resource_file

from mycroft.audio import is_speaking
from mycroft.client.speech.mic import MutableMicrophone, get_silence


class ResponsiveRecognizer(speech_recognition.Recognizer):
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    # Padding of silence when feeding to pocketsphinx
    SILENCE_SEC = 0.01

    # The minimum seconds of noise before a
    # phrase can be considered complete
    MIN_LOUD_SEC_PER_PHRASE = 0.5

    # The minimum seconds of silence required at the end
    # before a phrase will be considered complete
    MIN_SILENCE_AT_END = 0.25

    # The maximum seconds a phrase can be recorded,
    # provided there is noise the entire time
    RECORDING_TIMEOUT = 10.0

    # The maximum time it will continue to record silence
    # when not enough noise has been detected
    RECORDING_TIMEOUT_WITH_SILENCE = 3.0

    # Time between pocketsphinx checks for the wake word
    SEC_BETWEEN_WW_CHECKS = 0.2

    def __init__(self, hot_word_engines, config=None):
        self.config_core = config or {}
        listener_config = self.config_core.get("listener") or {}
        self.confirm_listening = self.config_core.get("confirm_listening", True)
        self.overflow_exc = listener_config.get('overflow_exception', False)
        self.use_wake_word = listener_config.get('wake_word_enabled', True)
        speech_recognition.Recognizer.__init__(self)
        self.audio = pyaudio.PyAudio()
        self.multiplier = listener_config.get('multiplier', 1.0)
        self.energy_ratio = listener_config.get('energy_ratio', 1.5)
        # check the config for the flag to save wake words.

        self.save_utterances = listener_config.get('save_utterances', False)

        self.save_wake_words = listener_config.get('record_wake_words', False)
        self.saved_wake_words_dir = join(gettempdir(), 'mycroft_wake_words')

        self.mic_level_file = os.path.join(get_ipc_directory(config=config),
                                           "mic_level")

        # Signal statuses
        self._stop_signaled = False
        self._listen_triggered = False
        self.hotword_engines = hot_word_engines or {}

        # The maximum audio in seconds to keep for transcribing a phrase
        # The wake word must fit in this time
        num_phonemes = 10
        # use number of phonemes from longest hotword
        for w in self.hotword_engines:
            try:
                phon = get_phonemes(w).split(" ")
                if len(phon) > num_phonemes:
                    num_phonemes = len(phon)
            except FailedToGuessPhonemes:
                LOG.error(f"Failed to guess phonemes for: {w}")
        len_phoneme = listener_config.get('phoneme_duration', 120) / 1000.0
        self.TEST_WW_SEC = num_phonemes * len_phoneme
        self.SAVED_WW_SEC = max(3, self.TEST_WW_SEC)

        self.audio_consumers = None

    def bind(self, audio_consumers):
        self.audio_consumers = audio_consumers

    def feed_hotwords(self, chunk):
        """ feed sound chunk to hotword engines that perform streaming
        predictions (precise) """
        for hw in self.hotword_engines:
            self.hotword_engines[hw]["engine"].update(chunk)

    def record_sound_chunk(self, source):
        return source.stream.read(source.CHUNK, self.overflow_exc)

    @staticmethod
    def calc_energy(sound_chunk, sample_width):
        return audioop.rms(sound_chunk, sample_width)

    def _record_phrase(
            self,
            source,
            sec_per_buffer,
            stream=None,
            ww_frames=None
    ):
        """Record an entire spoken phrase.

        Essentially, this code waits for a period of silence and then returns
        the audio.  If silence isn't detected, it will terminate and return
        a buffer of RECORDING_TIMEOUT duration.

        Args:
            source (MutableMicrophone):  Source producing the audio chunks
            sec_per_buffer (float):  Fractional number of seconds in each chunk
            stream (AudioStreamHandler): Stream target that will receive chunks
                                         of the utterance audio while it is
                                         being recorded.
            ww_frames (deque):  Frames of audio data from the last part of wake
                                word detection.

        Returns:
            bytearray: complete audio buffer recorded, including any
                       silence at the end of the user's utterance
        """

        num_loud_chunks = 0
        noise = 0

        max_noise = 25
        min_noise = 0

        silence_duration = 0

        def increase_noise(level):
            if level < max_noise:
                return level + 200 * sec_per_buffer
            return level

        def decrease_noise(level):
            if level > min_noise:
                return level - 100 * sec_per_buffer
            return level

        # Smallest number of loud chunks required to return
        min_loud_chunks = int(self.MIN_LOUD_SEC_PER_PHRASE / sec_per_buffer)

        # Maximum number of chunks to record before timing out
        max_chunks = int(self.RECORDING_TIMEOUT / sec_per_buffer)
        num_chunks = 0

        # Will return if exceeded this even if there's not enough loud chunks
        max_chunks_of_silence = int(self.RECORDING_TIMEOUT_WITH_SILENCE /
                                    sec_per_buffer)

        # bytearray to store audio in
        byte_data = get_silence(source.SAMPLE_WIDTH)

        if stream:
            stream.stream_start()

        phrase_complete = False

        while num_chunks < max_chunks and not phrase_complete:
            if ww_frames:
                chunk = ww_frames.popleft()
            else:
                chunk = self.record_sound_chunk(source)

            self.audio_consumers.feed_speech(self._create_audio_data(chunk,
                                                                     source))

            byte_data += chunk
            num_chunks += 1

            if stream:
                stream.stream_chunk(chunk)

            energy = self.calc_energy(chunk, source.SAMPLE_WIDTH)
            test_threshold = self.energy_threshold * self.multiplier
            is_loud = energy > test_threshold
            if is_loud:
                noise = increase_noise(noise)
                num_loud_chunks += 1
            else:
                noise = decrease_noise(noise)
                self._adjust_threshold(energy, sec_per_buffer)

            if num_chunks % 10 == 0:
                self.write_mic_level(energy, source)

            was_loud_enough = num_loud_chunks > min_loud_chunks

            quiet_enough = noise <= min_noise
            if quiet_enough:
                silence_duration += sec_per_buffer
                if silence_duration < self.MIN_SILENCE_AT_END:
                    quiet_enough = False  # gotta be silent for min of 1/4 sec
            else:
                silence_duration = 0
            recorded_too_much_silence = num_chunks > max_chunks_of_silence
            if quiet_enough and (was_loud_enough or recorded_too_much_silence):
                phrase_complete = True

            # Pressing top-button will end recording immediately
            if check_for_signal('buttonPress', config=self.config_core):
                phrase_complete = True

        return byte_data

    def write_mic_level(self, energy, source):
        with open(self.mic_level_file, 'w') as f:
            f.write('Energy:  cur={} thresh={:.3f} muted={}'.format(
                energy,
                self.energy_threshold,
                int(source.muted)
            )
            )

    @staticmethod
    def sec_to_bytes(sec, source):
        return int(sec * source.SAMPLE_RATE) * source.SAMPLE_WIDTH

    def _skip_wake_word(self):
        """
        Check if told programmatically to skip the wake word.
        For example when we are in a dialog with the user.
        """
        if self._listen_triggered:
            return True

        # Pressing the Mark 1 button can start recording (unless
        # it is being used to mean 'stop' instead)
        if check_for_signal('buttonPress', 1, config=self.config_core):
            # give other processes time to consume this signal if
            # it was meant to be a 'stop'
            sleep(0.25)
            if check_for_signal('buttonPress', config=self.config_core):
                # Signal is still here, assume it was intended to
                # begin recording
                LOG.debug("Button Pressed, wakeword not needed")
                return True

        if self.use_wake_word:
            return False
        else:
            return True

    def stop(self):
        """
            Signal stop and exit waiting state.
        """
        self._stop_signaled = True

    def _compile_metadata(self, hw):
        ww_module = self.hotword_engines[hw]["engine"].__class__.__name__
        if ww_module == 'PreciseHotword':
            model_path = self.hotword_engines[hw]["engine"].precise_model
            with open(model_path, 'rb') as f:
                model_hash = md5(f.read()).hexdigest()
        else:
            model_hash = '0'

        return {
            'name': self.hotword_engines[hw]["engine"].key_phrase.replace(' ',
                                                                          '-'),
            'engine': md5(ww_module.encode('utf-8')).hexdigest(),
            'time': str(int(1000 * get_time())),
            'model': str(model_hash)
        }

    def trigger_listen(self):
        """Externally trigger listening."""
        LOG.debug('Listen triggered from external source.')
        self._play_confirmation_sound()
        self._listen_triggered = True

    def _wait_until_wake_word(self, source, sec_per_buffer, bus):
        """Listen continuously on source until a wake word is spoken

        Args:
            source (MutableMicrophone):  Source producing the audio chunks
            sec_per_buffer (float):  Fractional number of seconds in each chunk
        """
        num_silent_bytes = int(self.SILENCE_SEC * source.SAMPLE_RATE *
                               source.SAMPLE_WIDTH)

        silence = get_silence(num_silent_bytes)

        # bytearray to store audio in
        byte_data = silence

        buffers_per_check = self.SEC_BETWEEN_WW_CHECKS / sec_per_buffer
        buffers_since_check = 0.0

        # Max bytes for byte_data before audio is removed from the front
        max_size = self.sec_to_bytes(self.SAVED_WW_SEC, source)
        test_size = self.sec_to_bytes(self.TEST_WW_SEC, source)

        said_wake_word = False

        # Rolling buffer to track the audio energy (loudness) heard on
        # the source recently.  An average audio energy is maintained
        # based on these levels.
        energies = []
        idx_energy = 0
        avg_energy = 0.0
        energy_avg_samples = int(5 / sec_per_buffer)  # avg over last 5 secs
        counter = 0

        # These are frames immediately after wake word is detected
        # that we want to keep to send to STT
        ww_frames = deque(maxlen=7)

        while not said_wake_word and not self._stop_signaled:
            if self._skip_wake_word():
                break
            chunk = self.record_sound_chunk(source)
            ww_frames.append(chunk)

            energy = self.calc_energy(chunk, source.SAMPLE_WIDTH)
            if energy < self.energy_threshold * self.multiplier:
                self._adjust_threshold(energy, sec_per_buffer)

            if len(energies) < energy_avg_samples:
                # build the average
                energies.append(energy)
                avg_energy += float(energy) / energy_avg_samples
            else:
                # maintain the running average and rolling buffer
                avg_energy -= float(energies[idx_energy]) / energy_avg_samples
                avg_energy += float(energy) / energy_avg_samples
                energies[idx_energy] = energy
                idx_energy = (idx_energy + 1) % energy_avg_samples

                # maintain the threshold using average
                if energy < avg_energy * 1.5:
                    if energy > self.energy_threshold:
                        # bump the threshold to just above this value
                        self.energy_threshold = energy * 1.2

            # Periodically output energy level stats.  This can be used to
            # visualize the microphone input, e.g. a needle on a meter.
            if counter % 3:
                self.write_mic_level(energy, source)
            counter += 1

            # At first, the buffer is empty and must fill up.  After that
            # just drop the first chunk bytes to keep it the same size.
            needs_to_grow = len(byte_data) < max_size
            if needs_to_grow:
                byte_data += chunk
            else:  # Remove beginning of audio and add new chunk to end
                byte_data = byte_data[len(chunk):] + chunk

            buffers_since_check += 1.0
            self.feed_hotwords(chunk)
            if buffers_since_check > buffers_per_check:
                buffers_since_check -= buffers_per_check
                chopped = byte_data[-test_size:] \
                    if test_size < len(byte_data) else byte_data
                audio_data = chopped + silence
                said_hot_word = False
                for hotword in self.check_for_hotwords(audio_data, source):
                    said_hot_word = True
                    engine = self.hotword_engines[hotword]["engine"]
                    sound = self.hotword_engines[hotword]["sound"]
                    utterance = self.hotword_engines[hotword]["utterance"]
                    listen = self.hotword_engines[hotword]["listen"]

                    LOG.debug("Hot Word: " + hotword)
                    # If enabled, play a wave file with a short sound to audibly
                    # indicate hotword was detected.
                    if sound:
                        self._play_confirmation_sound(sound, source)

                    # Hot Word succeeded
                    payload = {
                        'hotword': hotword,
                        'start_listening': listen,
                        'sound': sound,
                        "engine": engine.__class__.__name__
                    }
                    bus.emit("recognizer_loop:hotword", payload)

                    if utterance:
                        # send the transcribed word on for processing
                        payload = {
                            'utterances': [utterance]
                        }
                        bus.emit("recognizer_loop:utterance", payload)

                    mtd = self._compile_metadata(hotword)
                    if self.save_wake_words:
                        # Save wake word locally
                        audio = self._create_audio_data(byte_data, source)

                        if not isdir(self.saved_wake_words_dir):
                            os.mkdir(self.saved_wake_words_dir)

                        fn = join(
                            self.saved_wake_words_dir,
                            '_'.join(str(mtd[k]) for k in sorted(mtd)) + '.wav'
                        )
                        with open(fn, 'wb') as f:
                            f.write(audio.get_wav_data())

                    if listen:
                        said_wake_word = True

                if said_hot_word:
                    # reset bytearray to store wake word audio in, else many
                    # serial detections
                    byte_data = silence

    def _play_confirmation_sound(self, snd_file: Optional[str] = None, source: Optional[MutableMicrophone] = None):
        """
        Plays the specified snd_file (or default start_listening.wav). Optionally mutes the passed source.
        :param snd_file: Resource name of sound file to play (i.e. snd/start_listening.wav)
        :param source: Optional MutableMicrophone to mute while playing back audio
        """
        if self.confirm_listening:
            try:
                snd_file = snd_file or "snd/start_listening.wav"
                LOG.debug(snd_file)
                audio_file = resolve_resource_file(snd_file, config=self.config_core)
                if not audio_file:
                    audio_file = resolve_neon_resource_file(snd_file)
                if not audio_file:
                    LOG.error(f"Could not resolve {snd_file}")
                    return
                LOG.info(audio_file)
                if source:
                    source.mute()
                if audio_file.endswith(".wav"):
                    play_wav(audio_file).wait()
                elif audio_file.endswith(".mp3"):
                    play_mp3(audio_file).wait()
                elif audio_file.endswith(".ogg"):
                    play_ogg(audio_file).wait()
                if source:
                    source.unmute()
            except Exception as e:
                LOG.error(e)

    def check_for_hotwords(self, byte_data, source):
        # check hot word
        found = False
        audio_data = self._create_audio_data(byte_data, source)
        for hotword in self.hotword_engines:
            engine = self.hotword_engines[hotword]["engine"]
            if engine.found_wake_word(byte_data):
                self.audio_consumers.feed_hotword(audio_data)
                found = True
                yield hotword
        if not found:
            self.audio_consumers.feed_audio(audio_data)

    @staticmethod
    def _create_audio_data(raw_data, source):
        """
        Constructs an AudioData instance with the same parameters
        as the source and the specified frame_data
        """
        return AudioData(raw_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    def listen(self, source, bus, stream=None):
        """Listens for chunks of audio that Mycroft should perform STT on.

        This will listen continuously for a wake-up-word, then return the
        audio chunk containing the spoken phrase that comes immediately
        afterwards.

        Args:
            source (MutableMicrophone):  Source producing the audio chunks
            bus (EventEmitter): Emitter for notifications of when recording
                                    begins and ends.
            stream (AudioStreamHandler): Stream target that will receive chunks
                                         of the utterance audio while it is
                                         being recorded

        Returns:
            AudioData: audio with the user's utterance, minus the wake-up-word
        """
        assert isinstance(source, AudioSource), "Source must be an AudioSource"

        #        bytes_per_sec = source.SAMPLE_RATE * source.SAMPLE_WIDTH
        sec_per_buffer = float(source.CHUNK) / source.SAMPLE_RATE

        # Every time a new 'listen()' request begins, reset the threshold
        # used for silence detection.  This is as good of a reset point as
        # any, as we expect the user and Mycroft to not be talking.
        # NOTE: adjust_for_ambient_noise() doc claims it will stop early if
        #       speech is detected, but there is no code to actually do that.
        self.adjust_for_ambient_noise(source, 1.0)

        # If skipping wake words, just pass audio to our streaming STT
        # TODO: Check config updates?
        if stream and not self.use_wake_word:
            stream.stream_start()
            stream.has_result.clear()
            frame_data = get_silence(source.SAMPLE_WIDTH)
            LOG.debug("Stream starting!")
            while not stream.has_result.is_set():
                # Pass audio until STT tells us to stop (this is called again immediately)
                chunk = self.record_sound_chunk(source)
                if not is_speaking():
                    # Filter out Neon speech
                    stream.stream_chunk(chunk)
                    frame_data += chunk
            LOG.debug("stream ended!")
        # If using wake words, wait until the wake_word is detected and then record the following phrase
        else:
            LOG.debug("Waiting for wake word...")
            self._wait_until_wake_word(source, sec_per_buffer, bus)
            self._listen_triggered = False
            if self._stop_signaled:
                return

            LOG.debug("Recording...")
            bus.emit("recognizer_loop:record_begin")

            frame_data = self._record_phrase(source, sec_per_buffer, stream)

            bus.emit("recognizer_loop:record_end")

        # After the phrase is complete, save the audio frame_data and return it
        audio_data = self._create_audio_data(frame_data, source)

        # bus.emit("recognizer_loop:record_end")
        if self.save_utterances:
            LOG.info("Recording utterance")
            stamp = str(datetime.datetime.now())
            filename = "/tmp/mycroft_utterance%s.wav" % stamp
            with open(filename, 'wb') as filea:
                filea.write(audio_data.get_wav_data())
            LOG.debug("Thinking...")
        else:
            filename = None
        return audio_data, filename

    def _adjust_threshold(self, energy, seconds_per_buffer):
        if self.dynamic_energy_threshold and energy > 0:
            # account for different chunk sizes and rates
            damping = (
                    self.dynamic_energy_adjustment_damping ** seconds_per_buffer)
            target_energy = energy * self.energy_ratio
            self.energy_threshold = (
                    self.energy_threshold * damping +
                    target_energy * (1 - damping))
