#! /usr/bin/env python3
from setuptools import setup

setup(
    name                =   "pydocbrowser",
    version             =   '0.0',
    description         =   "Popular Python libraries API doc with pydoctor",
    author              =   "Martin Fischer",
    maintainer          =   "Tristan Landes",
    packages            =   ['pydocbrowser',],
    package_data        =   {'pydocbrowser': ['templates/*.html', 
                                              'pydoctor_templates/*.html',
                                              'pydoctor_templates/*.css']},
    install_requires    =   [
        "Jinja2", 
        "mistletoe", 
        "pydoctor @ git+https://github.com/twisted/pydoctor", # pydoctor latest
        "requests", 
        "toml", 
        "importlib_resources"
    ],
    python_requires=">=3.6",
)
