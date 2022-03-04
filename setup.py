import os

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))


setuptools.setup(
    name="coolpackets",
    version="0.0.2",
    author="Tim Woocker",
    author_email="tim.woocker@googlemail.com",
    description="Packet system for python TCP sockets.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/timwoocker/coolpackets",
    packages=setuptools.find_packages(exclude=["examples"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ]
)
