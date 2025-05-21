## Zammad Configuration for the Integreat Chat

To integrate Zammad, the following configuration has to be set:

1. Set up a Webhook to trigger the Integreat CMS on ticket updates. Set the target URL to `https://integreat-cms.example.com/api/v3/webhook/zammad/?token=$REGION_TOKEN`
1. Create a group `integreat-chat`. All new issues will be assigned to this group.
  * Set an e-mail address for the group
  * Disable the signature
1. Create a user for the Integreat CMS
  * Set the user e-mail to `tech+integreat-cms@tuerantuer.org`
  * Assign the user to the `integreat-chat` group.
  * Grant `Agent` and `Customer` roles.
1. Create additional required ticket attributes (Admin -> Objects -> Ticket):
  * Name: `automatic_answers`, Display: `Automatic Chatbot Answers`, Format: `Boolean Field`, True as default value
  * Name: `initial_response_sent`, Display: `Initial response sent`, Format: `Boolean field`, False as default value
  * Name: `evaluation_consent`, Display: `User agrees to chat evaluation`, Format: `Boolean field`, False as default value
1. Create an access token for the Integreat CMS user (`tech+integreat-cms@tuerantuer.org`) with permission `Agent tickets`
1. Create the Zammad triggers for the Integreat CMS webhook:
  * Conditions: `Action is updated`, `Subject contains not "automatically generated message"`
  * Execute: webhook configured above
1. The initial response for each chat is returned by a Zammad trigger. For each language, add a trigger named `Auto Response [$LANG]`, example is `EN`
  * Conditions: `State is new`, `Action is updated`, `Subject contains not "automatically generated message"`, `Title contains [EN]`, `Initial response is no`
  * Execute: `Note`, `visibility public`, `Subject "automatically generated message"`, `Initial response sent yes`, add a suitable message in the body.
    * Example message: `Welcome to the [Chat](https://integreat.app/testumgebung-e2e/en/welcome/welcome-to-stadt/the-integreat-chat) of [Integreat $REGION_NAME](https://integreat.app/testumgebung-e2e/en/welcome/welcome-to-stadt/about-integreat). Our team responds on weekdays, while our chatbot provides summary answers from linked pages. Read the linked pages to verify important information. This chat cannot help in [emergencies](https://webnext.integreat.app/testumgebung-e2e/en/health/emergency-numbers-sos).` A template for the info page can be found in the [info page template](INFO_TEMPLATE.md)
    * Trick for translating link descriptions: save message in docx file and use Google Translate for documents. Then download the document and update the link target. This can then be pasted into the trigger.
1. Add a weekly scheduler to delete old tickets:
  * Run once a week
  * Conditions: `state is closed`, `Closing time before (relative) 3 months`
  * Action: delete
  * Disable Notifications: yes
1. Add a scheduler to close old tickets:
  * Run once a week
  * Conditions: `state is open or new`, `Last contact (customer) before (relative) 1 months`
  * Action: `State closed`
  * Disable Notifications: yes
