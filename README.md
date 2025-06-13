# trace-shrink

A tool to analyze captures of ABR streams (HAR or Proxyman).

See the documentation for more details: https://wabiloo.github.io/trace-shrink/

## Documentation

This project uses [MkDocs](https://www.mkdocs.org/) and the [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme for its documentation.

### Running the documentation server

To view the documentation locally, you first need to install the project dependencies. It is recommended to do this in a virtual environment. `uv` is used for dependency management.

1.  Install dependencies:
    ```bash
    uv sync --dev
    ```

2.  Start the local documentation server:
    ```bash
    uv run docs
    ```

You can now access the documentation at `http://127.0.0.1:8000`. The server will automatically reload when you make changes to the documentation files in the `docs` directory.
