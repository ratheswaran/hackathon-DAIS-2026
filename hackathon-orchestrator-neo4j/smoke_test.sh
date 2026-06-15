#!/usr/bin/env bash
# Smoke test the hackathon orchestrator serving endpoint.
#
# Sends a single ResponsesAgent-shaped request and prints the response.
# Use after `./deploy.sh` succeeds and the endpoint state is READY.
#
# Usage:
#   ./smoke_test.sh                       # default Sudan crisis prompt
#   ./smoke_test.sh "What is X in 2023?"  # custom prompt
#   ./smoke_test.sh --endpoint <name>     # query a different endpoint
#   ./smoke_test.sh --raw                 # dump raw JSON instead of pretty
#
# Env overrides:
#   PROFILE       (default: hackathon-test)
#   ENDPOINT_NAME (default: agents_workspace-hackathon-orchestrator_agent_neo4j)

set -euo pipefail

PROFILE="${PROFILE:-hackathon-test}"
ENDPOINT_NAME="${ENDPOINT_NAME:-agents_workspace-hackathon-orchestrator_agent_neo4j}"
RAW=0
PROMPT="What are the top host countries for Sudanese refugees in 2024? Keep the answer to 3-4 sentences."

while [ $# -gt 0 ]; do
  case "$1" in
    --endpoint) ENDPOINT_NAME="$2"; shift 2 ;;
    --raw)      RAW=1; shift ;;
    -h|--help)  sed -n '2,18p' "$0"; exit 0 ;;
    *)          PROMPT="$1"; shift ;;
  esac
done

echo "Endpoint : $ENDPOINT_NAME"
echo "Prompt   : $PROMPT"
echo "Profile  : $PROFILE"
echo "---"

# ResponsesAgent input shape — matches the agent's input_example.
REQUEST=$(python3 -c "
import json, uuid
print(json.dumps({
    'input': [{'role': 'user', 'content': '''$PROMPT'''}],
    'context': {'conversation_id': f'smoke-{uuid.uuid4().hex[:8]}'},
}))")

RESPONSE=$(databricks serving-endpoints query "$ENDPOINT_NAME" \
  --json "$REQUEST" --profile "$PROFILE" 2>&1)

if [ "$RAW" -eq 1 ]; then
  echo "$RESPONSE"
  exit 0
fi

echo "$RESPONSE" | python3 -c "
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    print('(could not parse response as JSON — raw output:)')
    print(raw)
    sys.exit(1)

# ResponsesAgent output shape: {'output': [<items>]} where each item has a
# type. Extract text items for readability.
texts = []
for item in d.get('output', []):
    t = item.get('type') or item.get('role') or '<unknown>'
    if t in ('message', 'text', 'response.output_item.done'):
        content = item.get('content')
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('text'):
                    texts.append(c['text'])
                elif isinstance(c, str):
                    texts.append(c)
        elif isinstance(content, str):
            texts.append(content)
        elif 'text' in item:
            texts.append(item['text'])

if texts:
    print('--- response text ---')
    print('\n'.join(texts))
else:
    print('--- raw response (no text items found) ---')
    print(json.dumps(d, indent=2)[:2000])
"
