#! /usr/bin/env python3
from setuptools import setup

setup(
    name                =   "pydocbrowser",
    version             =   '0.0',
    description         =   "Consistent API docs for Python with pydoctor",
    author              =   "Martin Fischer",
    maintainer          =   "Tristan Landes",
    packages            =   ['pydocbrowser',],
    package_data        =   {'pydocbrowser': ['templates/*.html', 
                                              'pydoctor_templates/*.html',
                                              'pydoctor_templates/*.css']},
    install_requires    =   [
        "Jinja2", 
        "mistletoe", 
        "pydoctor @ git+https://github.com/twisted/pydoctor@845fabdcec05013b4727637b4e3183d59a14fcd8#egg=pydoctor", # With search bar
        "requests", 
        "toml", 
        "importlib_resources"
    ],
    python_requires=">=3.6",
)
