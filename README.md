# pydoc.dev - consistent API docs for Python

Looking at the API documentations of Python packages can be a bit disorienting
because they can look different from project to project (since different
projects use different [Sphinx] themes) and because the API documentation
often is not structured after the Python modules.

**pydoc.dev** strives to be for Python what [docs.rs] is for Rust.
It works by downloading the source files from the [Python Package Index],
the API documentation is then generated with [pydoctor].

[Sphinx]: https://www.sphinx-doc.org/
[docs.rs]: https://docs.rs/
[Python Package Index]: https://pypi.org/
[pydoctor]: https://github.com/twisted/pydoctor
