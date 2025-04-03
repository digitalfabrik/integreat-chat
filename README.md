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

## Zammad Integration

To integrate Zammad, the following configuration has to be set:

* Webhook to `https://integreat-cms.example.com/api/v3/webhook/zammad/?token=$REGION_TOKEN`
* Create a group `integreat-chat`. All new issues will be assigned to this group.
  * Set an e-mail address for the group
  * Disable the signature
* Create a user for the Integreat CMS
  * Set the user e-mail to `tech+integreat-cms@tuerantuer.org`
  * Assign the user to the `integreat-chat` group.
  * Grant `Agent` and `Customer` roles.
* Ticket attributes (Admin -> Objects -> Ticket):
  * Name: `automatic_answers`, Display: `Automatic Chatbot Answers`, Format: `Boolean Field`, True as default value
  * Name: `initial_response_sent`, Display: `Initial response sent`, Format: `Boolean field`, False as default value
  * Name: `evaluation_consent`, Display: `User agrees to chat evaluation`, Format: `Boolean field`, False as default value
* Create an access token for the Integreat CMS user with permission `Agent tickets`
* Trigger for webhook:
  * Conditions: `Action is updated`, `Subject contains not "automatically generated message"`
  * Execute: webhook configured above
* Auto response for new tickets in each language, exmple is `EN`
  * Conditions: `State is new`, `Action is updated`, `Subject contains not "automatically generated message"`, `Title contains [EN]`, `Initial response is no`
  * Execute: `Note`, `visibility public`, `Subject "automatically generated message"`, `Initial response sent yes`, add a suitable message in the body.
    * Example message: `Welcome to Integreat Chat $REGION_NAME in $LANGUAGE. Our team responds on weekdays, while our chatbot provides summary answers from linked articles, which you should use to verify important information. This chat cannot help in [emergencies](https://webnext.integreat.app/testumgebung-e2e/en/health/emergency-numbers-sos).`
* Scheduler to delete old tickets:
  * Run once a week
  * Conditions: `state is closed`, `Closing time before (relative) 3 months`
  * Action: delete
  * Disable Notifications: yes

