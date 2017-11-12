from setuptools import setup

setup(
    name='rpi_metar',
    py_modules=['rpi_metar'],
    version='0.1',
    description='Visualizing METAR data on a Raspberry Pi with LEDs.',
    keywords = ['METAR', 'Raspberry Pi'],
    author='Scott Sturdivant',
    author_email='scott.sturdivant@gmail.com',
    license='MIT',
    url='https://pypi.python.org/pypi/rpi_metar',
    long_description=open('README.md', 'r').read(),
    install_requires=open('requirements.txt', 'r').read(),
    entry_points={
        'console_scripts': [
            'rpi_metar = rpi_metar:main',
        ],
    },
)
