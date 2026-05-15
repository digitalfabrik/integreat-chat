#!/usr/bin/env bash
set -euo pipefail

region_slug=$1
info_url=$2
emergency_url=$3

msg="Welcome to <a href=\"${info_url}\">Frag Integreat</a> Landkreis Rottweil. \
This assistant helps you to find information. Read the linked pages to verify important information. \
This chat cannot help in <a href=\"${emergency_url}\">emergencies</a>."

payload=$(jq -nc \
          --arg r "$region_slug" \
          --arg m "$msg" \
          '{source_language:"en",region:$r,message:$m}')
resp=$(curl -s -X POST \
        https://igchat-inference.tuerantuer.org/translate/message_to_region_languages/ \
        -d "$payload" -H 'Content-Type: application/json')

echo "$resp" | jq .

len=$(echo "$resp" | jq '.translations | length')

echo "Len: $len"

ruby_tpl=$(cat <<'RUBY'
# frozen_string_literal: true
email_channel = Channel.find_by(name: 'Email')
admin_user    = User.find_by(role: 'Admin')
Trigger.find_or_initialize_by(name: "Send initial message (__LANG__)" ).update!(
  condition: {
    'ticket.action' => { 'operator' => 'is', 'value' => 'create' }
  },
  perform: {
    'article.create' => {
      'subject'    => 'Welcome',
      'body'       => '__BODY__',
      'type'       => 'email',
      'internal'   => false,
      'sender'     => 'System',
      'channel_id' => email_channel.id
    }
  },
  disable_notification: false,
  note: '',
  activator: 'action',
  execution_condition_mode: 'selective',
  active: true,
  updated_by_id: admin_user.id,
  created_by_id: admin_user.id
)
puts "Trigger for __LANG__ created/updated."
RUBY
)

echo "Iterating ..."

for i in $(seq 0 $(($len - 1))); do
    lang=$(echo "$resp" | jq -r ".translations[$i].language")
    trans=$(echo "$resp" | jq -r ".translations[$i].translation")
    escaped_trans=${trans//\'/\\\'}
    ruby_content="${ruby_tpl//__LANG__/$lang}"
    ruby_content="${ruby_content//__BODY__/$escaped_trans}"
    outfile="scripts/trigger_${lang}.rb"
    echo "$ruby_content" > "$outfile"
    echo "✅ Generated $outfile (language: $lang)"
done

echo "All trigger files created."
echo "Run them with:"
echo "  bundle exec rails runner scripts/trigger_*.rb"
