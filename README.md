# About

RAG/LLM supported online migration counseling service & improved Integreat search engine. It integrates as a chat service into the [Integreat App](https://github.com/digitalfabrik/integreat-app) and presents requests in a Zammad to counselors. The solution aims to be privacy friendly by not using any third party LLM services.

This project is currently in a research and development phase. The code created for this repo aims to be compatible for future integration into the [Integreat CMS](https://github.com/digitalfabrik/integreat-cms). For the time being the code is separated for faster iteration and testing.

Major issues that have to be addressed:

- Support for low ressource languages
- Code mixing
- Language detection
- Translations

# Start Project
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

# Configuration

## Back End

* Deploy as normal Django application. No database is needed.

## Zammad

For details about the Zammad configuration, read the [ZAMMAD_CONFIG.md](./ZAMMAD_CONFIG.md)


