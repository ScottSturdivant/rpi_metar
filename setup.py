from setuptools import setup

try:
    from pypandoc import convert

    def read_md(f): return convert(f, 'rst')

except ImportError:
    print("warning: pypandoc module not found, could not convert Markdown to RST")

    def read_md(f): return open(f, 'r').read()

setup(
    name='rpi_metar',
    py_modules=['rpi_metar'],
    version='0.1.4',
    description='Visualizing METAR data on a Raspberry Pi with LEDs.',
    keywords=['METAR', 'Raspberry Pi'],
    author='Scott Sturdivant',
    author_email='scott.sturdivant@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    url='https://github.com/ScottSturdivant/rpi_metar',
    long_description=read_md('README.md'),
    install_requires=open('requirements.txt', 'r').read(),
    entry_points={
        'console_scripts': [
            'rpi_metar = rpi_metar:main',
        ],
    },
    python_requires='>=3',
)
