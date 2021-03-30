from setuptools import setup

setup(
    name='neon_speech',
    version='0.1.1',
    packages=['neon_speech', 'neon_speech.plugins',
              'neon_speech.plugins.modules',
              'neon_speech.plugins.modules.background',
              'neon_speech.plugins.modules.audio_normalizer'],
    url='https://github.com/NeonJarbas/neon_speech',
    license='',
    install_requires=["requests",
                      "pyaudio",
                      "mycroft-messagebus-client>=0.8.4",
                      "SpeechRecognition==3.8.1",
                      "ovos_utils",
                      "pydub"],
    author='jarbasAi',
    author_email='jarbasai@mailfence.com',
    description='speech client for Neon',
    entry_points={
        'console_scripts': [
            'neon_speech_client=neon_speech.__main__:main'
        ]
    }
)
