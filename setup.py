from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

with open("./version.py", "r", encoding="utf-8") as v:
    for line in v.readlines():
        if line.startswith("__version__"):
            if '"' in line:
                version = line.split('"')[1]
            else:
                version = line.split("'")[1]

with open("./requirements.txt", "r", encoding="utf-8") as r:
    requirements = r.readlines()

setup(
    name='neon_speech',
    version=version,
    packages=['neon_speech', 'neon_speech.plugins',
              'neon_speech.plugins.modules',
              'neon_speech.plugins.modules.background',
              'neon_speech.plugins.modules.audio_normalizer'],
    url='https://github.com/NeonGeckoCom/neon_speech',
    license='NeonAI License v1.0',
    install_requires=requirements,
    author='Neongecko',
    author_email='developers@neon.ai',
    description=long_description,
    entry_points={
        'console_scripts': [
            'neon_speech_client=neon_speech.__main__:main'
        ]
    }
)
