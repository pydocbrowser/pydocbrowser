# Consistent API docs for Python with pydoctor

Looking at the API documentations of Python packages can be a bit disorienting
because they can look different from project to project (since different
projects use different [Sphinx] themes) and because the API documentation
often is not structured after the Python modules.

**pydocbrowser** builds bunch of popular projects API documentation and provide
single documentation entry point for developers. Does a bit like what [docs.rs] is doing for Rust.

It works by downloading the source files from the [Python Package Index],
the API documentation is then generated with [pydoctor].

This solftware is based on pre-alpha version of [pydoc.dev](https://git.push-f.com/pydoc.dev/).

<!-- package list -->

## How to contribute

* You can give feedback and suggest packages to be included, please
  open a Github issue.

* You can contribute to [pydoctor].

* You can contribute to the individual Python projects
  to improve their [docstrings].

[Sphinx]: https://www.sphinx-doc.org/
[docs.rs]: https://docs.rs/
[Python Package Index]: https://pypi.org/
[pydoctor]: https://github.com/twisted/pydoctor
[#pydoc]: https://web.libera.chat/?channel=#pydoc
[Libera.Chat]: https://libera.chat/
[docstrings]: https://www.python.org/dev/peps/pep-0257/
