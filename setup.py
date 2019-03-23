from setuptools import setup, find_packages

try:
    from pypandoc import convert

    def read_md(f): return convert(f, 'rst')

except ImportError:
    print("warning: pypandoc module not found, could not convert Markdown to RST")

    def read_md(f): return open(f, 'r').read()

###############################################################################

NAME = 'rpi_metar'
PACKAGES = find_packages()
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
]

###############################################################################

setup(
    name=NAME,
    version='0.3.3',
    packages=PACKAGES,
    include_package_data=True,
    description='Visualizing METAR data on a Raspberry Pi with LEDs.',
    keywords=['METAR', 'Raspberry Pi'],
    author='Scott Sturdivant',
    author_email='scott.sturdivant@gmail.com',
    license='MIT',
    classifiers=CLASSIFIERS,
    url='https://github.com/ScottSturdivant/rpi_metar',
    long_description=read_md('README.md'),
    install_requires=open('requirements.txt', 'r').read(),
    entry_points={
        'console_scripts': [
            'rpi_metar = rpi_metar.core:main',
            'rpi_metar_init = rpi_metar.scripts.init:main',
        ],
    },
    python_requires='>=3',
    zip_safe=False,
)
