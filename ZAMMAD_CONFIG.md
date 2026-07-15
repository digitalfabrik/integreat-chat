## Zammad Configuration for the Integreat Chat

To integrate Zammad, the following configuration has to be set:

1. Set up an Email channel
1. Set up a Webhook to trigger the Integreat CMS on ticket updates. Set the target URL to `https://integreat-cms.example.com/api/v3/webhook/zammad/?token=$REGION_TOKEN`. The token can be obtained in the Integreat CMS region settings. Rails command in `zammad run rails console`:
   ```ruby
   UserInfo.current_user_id = 1

   Webhook.create!(
     name:        "Integreat CMS",
     endpoint:    "https://integreat-cms.example.com/api/v3/webhook/zammad/?token=$REGION_TOKEN",
     ssl_verify:  true,
     active:      true,
     note:        "Triggers the Integreat CMS on ticket updates",
   )
   ```
1. Create a group `integreat-chat`. All new issues will be assigned to this group.
   * Set an e-mail address for the group
   * Disable the signature
1. Create a user for the Integreat CMS
   * Set the user e-mail to `tech+integreat-cms@tuerantuer.org`
   * Assign the user to the `integreat-chat` group with full permissions.
   * Grant `Agent` and `Customer` roles.
   * Disable all mail notifications for this user.
1. Create additional required ticket attributes (Admin -> Objects -> Ticket):
   * Name: `automatic_answers`, Display: `Automatic Chatbot Answers`, Format: `Boolean Field`, True as default value
   * Name: `initial_response_sent`, Display: `Initial response sent`, Format: `Boolean field`, False as default value
   * Name: `evaluation_consent`, Display: `User agrees to chat evaluation`, Format: `Boolean field`, False as default value
   * Alternatively, use this rails command in `zammad run rails console`:
     ```ruby
     UserInfo.current_user_id = 1
     # 1. automatic_answers - Automatic Chatbot Answers (default: true)
     ObjectManager::Attribute.add(
       force:       true,
       object:      'Ticket',
       name:        'automatic_answers',
       display:     'Automatic Chatbot Answers',
       data_type:   'boolean',
       data_option: {
         default:    true,
         options:    {
           true  => 'yes',
           false => 'no',
         },
         null:       true,
         translate:  true,
       },
       active:        true,
       screens:       {
         create_middle: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
         edit: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
       },
       position:      1550,
       editable:      true,
       to_migrate:    false,
     )

     ObjectManager::Attribute.migration_execute
     attr = ObjectManager::Attribute.find_by(name: "automatic_answers")
     attr.to_migrate = true
     attr.to_create  = true
     attr.save!

     # 2. initial_response_sent - Initial response sent (default: false)
     ObjectManager::Attribute.add(
       force:       true,
       object:      'Ticket',
       name:        'initial_response_sent',
       display:     'Initial response sent',
       data_type:   'boolean',
       data_option: {
         default:    false,
         options:    {
           true  => 'yes',
           false => 'no',
         },
         null:       true,
         translate:  true,
       },
       active:        true,
       screens:       {
         create_middle: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
         edit: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
       },
       position:      1551,
       editable:      true,
       to_migrate:    false,
     )

     ObjectManager::Attribute.migration_execute
     attr = ObjectManager::Attribute.find_by(name: "initial_response_sent")
     attr.to_migrate = true
     attr.to_create  = true
     attr.save!

     # 3. evaluation_consent - User agrees to chat evaluation (default: false)
     ObjectManager::Attribute.add(
       force:       true,
       object:      'Ticket',
       name:        'evaluation_consent',
       display:     'User agrees to chat evaluation',
       data_type:   'boolean',
       data_option: {
         default:    false,
         options:    {
           true  => 'yes',
           false => 'no',
         },
         null:       true,
         translate:  true,
       },
       active:        true,
       screens:       {
         create_middle: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
         edit: {
           'ticket.agent'    => { shown: true, required: false },
           'ticket.customer' => { shown: false, required: false },
         },
       },
       position:      1552,
       editable:      true,
       to_migrate:    false,
     )

     ObjectManager::Attribute.migration_execute
     attr = ObjectManager::Attribute.find_by(name: "evaluation_consent")
     attr.to_migrate = true
     attr.to_create  = true
     attr.save!

     ObjectManager::Attribute.migration_execute(false)
     ```
     Exit the rails console to reload new models when done with this step!
1. Create an access token for the Integreat CMS user (`tech+integreat-cms@tuerantuer.org`) with permission `Agent tickets`
1. Create the Zammad trigger for the Integreat CMS webhook:
   * Conditions: `Action is updated`, `Subject contains not "automatically generated message"`
   * Execute: webhook configured above
   * Alternatively, use this rails command in `zammad run rails console`:
     ```ruby
     UserInfo.current_user_id = 1

     webhook = Webhook.find_by(name: "Integreat CMS")

     Trigger.create!(
       name:      "Notify Integreat CMS on ticket update",
       condition: {
         "ticket.action" => {
           "operator" => "is",
           "value"    => "update",
         },
         "article.subject" => {
           "operator" => "contains not",
           "value"    => "automatically generated message",
         },
       },
       perform: {
         "notification.webhook" => {
           "webhook_id" => webhook.id.to_s,
         },
       },
       active:                   true,
       execution_condition_mode: "selective",
     )
     ```
1. The initial response for each chat is returned by a Zammad trigger. For each language, add a trigger named `Auto Response [$LANG]`, example is `EN`
   * Conditions: `State is new`, `Action is updated`, `Subject contains not "automatically generated message"`, `Title contains [EN]`, `Initial response is no`
   * Execute: `Note`, `visibility public`, `Subject "automatically generated message"`, `Initial response sent yes`, add a suitable message in the body.
      * Example message: `Welcome to <a href=\"https://integreat.app/testumgebung-frag-integreat/en/ask-integreat\">Frag Integreat</a> Testumgebung Frag Integreat. This assistant helps you to find information. Read the linked pages to verify important information. This chat cannot help in <a href=\"https://integreat.app/testumgebung-frag-integreat/en/emergencies-sos/emergency-numbers\">emergencies</a>.` A template for the info page can be found in the [info page template](INFO_TEMPLATE.md)
      * Alternatively, use this rails command in `zammad run rails console`:
        ```ruby
        UserInfo.current_user_id = 1

        lang  = "EN"
        title = "Auto Response [EN]"

        body = "EN"

        Trigger.create!(
          name:      title,
          condition: {
            "ticket.state_id" => {
              "operator" => "is",
              "value"    => Ticket::State.find_by(name: "new").id.to_s,
            },
            "ticket.action" => {
              "operator" => "is",
              "value"    => "update",
            },
            "article.subject" => {
              "operator" => "contains not",
              "value"    => "automatically generated message",
            },
            "ticket.title" => {
              "operator" => "contains",
              "value"    => "[#{lang}]",
            },
            "ticket.initial_response_sent" => {
              "operator" => "is",
              "value"    => false,
            },
          },
          perform: {
            "article.note" => {
              "subject"  => "automatically generated message",
              "internal" => "false",
              "body"     => body,
            },
            "ticket.initial_response_sent" => {
              "value" => true,
            },
          },
          active:                   true,
          execution_condition_mode: "selective",
        )

        puts "Trigger \"#{title}\" created successfully!"
        ```
      * Use the translate API to translate the message into all languages for the relevant region:
        ```
        curl -s -X POST https://igchat-inference.tuerantuer.org/translate/message_to_region_languages/ -d'{"source_language":"en","region":"testumgebung":"Message with Integreat links"}' -H 'Content-Type: application/json' | jq '.translations[] | .translation' -r
        ```
        You can use `echo "message" | xclip -selection clipboard -t text/html` to transform the output into HTML in the clipboard.
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

     ```
     new_id     = Ticket::State.lookup(name: 'new').id.to_s
     open_id    = Ticket::State.lookup(name: 'open').id.to_s
     closed_id  = Ticket::State.lookup(name: 'closed').id.to_s

     timeplan = {
       'days'    => { 'Mon' => true, 'Tue' => false, 'Wed' => false, 'Thu' => false, 'Fri' => false, 'Sat' => false, 'Sun' => false },
       'hours'   => { '0' => false, '1' => false, '2' => false, '3' => true, '4' => false, '5' => false, '6' => false, '7' => false, '8' => false, '9' => false, '10' => false, '11' => false, '12' => false, '13' => false, '14' => false, '15' => false, '16' => false, '17' => false, '18' => false, '19' => false, '20' => false, '21' => false, '22' => false, '23' => false },
       'minutes' => { '0' => true, '10' => false, '20' => false, '30' => false, '40' => false, '50' => false },
     }

     Job.create_or_update(
       name: 'Delete closed chats after 3 months',
       object: 'Ticket',
       timeplan: timeplan,
       condition: {
         'ticket.state_id' => { 'operator' => 'is', 'value' => [open_id, closed_id] },
         'ticket.close_at' => { 'operator' => 'before (relative)', 'value' => '3', 'range' => 'month' },
       },
       perform: {
         'ticket.action' => { 'value' => 'delete' },
       },
       disable_notification: true,
       active: true,
       updated_by_id: 1,
       created_by_id: 1,
     )

     Job.create_or_update(
       name: 'Auto close inactive chats after 1 month',
       object: 'Ticket',
       timeplan: timeplan,
       condition: {
         'ticket.state_id'                 => { 'operator' => 'is', 'value' => [new_id, open_id] },
         'ticket.last_contact_customer_at' => { 'operator' => 'before (relative)', 'value' => '1', 'range' => 'month' },
       },
       perform: {
         'ticket.state_id' => { 'value' => closed_id },
       },
       disable_notification: true,
       active: true,
       updated_by_id: 1,
       created_by_id: 1,
     )

     puts 'Done. Current jobs:'
     Job.all.pluck(:id, :name, :active).each { |j| puts j.inspect }
     ```
