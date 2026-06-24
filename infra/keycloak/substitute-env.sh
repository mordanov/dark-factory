#!/bin/bash
set -e
INPUT="/opt/keycloak-import-src/realm-export.json"
OUTPUT="/opt/keycloak/data/import/realm.json"

cp "$INPUT" "$OUTPUT"

# Explicit substitution of each variable to prevent accidental replacement of
# unrelated ${...} patterns inside the JSON.
for var in \
  KC_BOOTSTRAP_ADMIN_USERNAME KC_BOOTSTRAP_ADMIN_EMAIL KC_BOOTSTRAP_ADMIN_PASSWORD \
  OAUTH2_PROXY_CLIENT_SECRET KC_ORCHESTRATOR_CLIENT_SECRET KC_DISTILLER_CLIENT_SECRET \
  KC_DISPATCHER_CLIENT_SECRET KC_AGENT_TOOLS_CLIENT_SECRET KC_UIM_CLIENT_SECRET \
  KC_TM_CLIENT_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET \
  UIM_FRONTEND_URL TM_FRONTEND_URL; do
  eval "val=\$$var"
  # Escape & / \ for sed RHS
  escaped=$(printf '%s' "$val" | sed 's/[&/\]/\\&/g')
  sed -i "s|\${${var}}|${escaped}|g" "$OUTPUT"
done

echo "[Keycloak] Realm JSON substituted → $OUTPUT"
