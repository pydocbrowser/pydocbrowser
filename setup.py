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
        "pydoctor @ git+https://github.com/twisted/pydoctor@157221fd6bedb43c07bccd1e188481e07c3c696c#egg=pydoctor", # With search bar
        "requests", 
        "toml", 
        "importlib_resources"
    ],
    python_requires=">=3.6",
)
