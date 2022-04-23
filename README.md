# Popular Python libraries API doc with pydoctor

## What is this

This is basically a primer for [pydoctor]. 

It builds bunch of popular projects API documentation and provide
single documentation entry point for developers.

It works by downloading the source files from the [Python Package Index].

## Why

Looking at the API documentations of Python packages can be a bit disorienting
because they can look different from project to project (since different
projects use different [Sphinx] themes) and because the API documentation
often is not structured after the Python modules. Using pydoctor enforces consistency
in the API documentation.

<!-- package list -->

## Install

You can use this software locally to build the documentation of any PyPI packages.

Install ``pydocbrowser`` from GitHub:

```
python3 -m pip install git+https://github.com/pydocbrowser/pydocbrowser.git
```

Quickly generate the docs for the ``requests`` module, use:

```
python3 -m pydocbrowser --package requests
```

It will create a folder ``build`` and place all HTML files inside ``build/www``. Create a ``packages.toml`` file to configure pydoctor options.

## How to contribute

* You can give feedback and suggest packages to be included, please
  open a [Github issue](https://github.com/pydocbrowser/pydocbrowser/issues).

* You are more than welcome to contribute to [pydoctor].

* You can contribute to the individual Python projects
  to improve their [docstrings].

## Note

This software is based on [pydoc.dev](https://git.push-f.com/pydoc.dev/).

[Sphinx]: https://www.sphinx-doc.org/
[docs.rs]: https://docs.rs/
[Python Package Index]: https://pypi.org/
[pydoctor]: https://github.com/twisted/pydoctor
[#pydoc]: https://web.libera.chat/?channel=#pydoc
[Libera.Chat]: https://libera.chat/
[docstrings]: https://www.python.org/dev/peps/pep-0257/
