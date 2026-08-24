# About

RAG/LLM supported online migration counseling service & improved Integreat search engine. It integrates as a chat service into the [Integreat App](https://github.com/digitalfabrik/integreat-app) and presents requests in a Zammad to counselors. The solution aims to be privacy friendly by not using any third party LLM services.

This project is currently in a research and development phase. The code created for this repo aims to be compatible for future integration into the [Integreat CMS](https://github.com/digitalfabrik/integreat-cms). For the time being the code is separated for faster iteration and testing.

Major issues that have to be addressed:

- Support for low ressource languages
- Code mixing
- Language detection
- Translations

# Start Project

## System requirements

The OCR pipeline (`docling` → `rapidocr` → OpenCV/`cv2`) links against a few
native system libraries. Without them the server still starts, but OCR fails at
runtime with:

```text
ImportError: libxcb.so.1: cannot open shared object file: No such file or directory
```

On Debian/Ubuntu, install them **before** running the app:

```bash
apt-get update
apt-get install -y libxcb1 libgl1 libglib2.0-0
```

| Package       | Provides                          | Why                                       |
|---------------|-----------------------------------|-------------------------------------------|
| `libxcb1`     | `libxcb.so.1`                     | OpenCV links against X11 (`X C Bindings`) |
| `libgl1`      | `libGL.so.1`, `libGLX.so.1`       | OpenGL runtime used by OpenCV             |
| `libglib2.0-0`| `libglib-2.0.so.0`, `libgthread`  | Glib used by OpenCV's I/O layer           |

On RHEL/CentOS/Fedora the equivalents are: `libxcb mesa-libGL glib2`.

> Note: on Debian 13 (trixie) `libglib2.0-0` is provided as `libglib2.0-0t64`,
> but installing `libglib2.0-0` works there too — it's a transitional package
> that pulls in the `t64` variant.

1. Install a virtual environment and activate it
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```
1. Install all dependencies
   ```
   pip install .
   ```
1. Run the server:
   ```
   cd integreat_chat
   python3 manage.py migrate
   python3 manage.py runserver
   ```

   Several views are `async def` (e.g. `bescheidcheck.analyze`) and
   require an ASGI server. For production use:

   ```
   uvicorn integreat_chat.core.asgi:application --host 0.0.0.0 --port 8000
   # or, with gunicorn:
   gunicorn --worker-class uvicorn.workers.UvicornWorker \
       integreat_chat.core.asgi:application --bind 0.0.0.0:8000
   ```

# Configuration

## Back End

* Deploy as normal Django application. No database is needed.

## Zammad

For details about the Zammad configuration, read the [ZAMMAD_CONFIG.md](./ZAMMAD_CONFIG.md)
