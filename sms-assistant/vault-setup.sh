#!/usr/bin/env bash
# Run this on macmini with VAULT_ADDR + a working admin token exported -
# same pattern as alexa-shopping-sync/vault-setup.sh one door down.
set -e

# 1. Generate a dedicated keypair for RESET's SSH access to eink.lan (not
#    Ed's personal key, not the CI-only key from sift-sms-gateway's setup -
#    this one's used at runtime by the running container, not CI).
KEY_DIR=$(mktemp -d)
ssh-keygen -t ed25519 -f "$KEY_DIR/eink_reset_key" -N "" -C "sift-sms-assistant-reset" >/dev/null

vault kv put secret/sift-sms-assistant \
  eink_ssh_key="$(cat "$KEY_DIR/eink_reset_key")"

# 2. Policy: read-only on just this one secret
vault policy write sift-sms-assistant - <<'EOF'
path "secret/data/sift-sms-assistant" {
  capabilities = ["read"]
}
EOF

# 3. JWT role bound to this specific Nomad job's workload identity
vault write auth/jwt-nomad/role/sift-sms-assistant - <<'EOF'
{
  "role_type": "jwt",
  "bound_audiences": "vault.io",
  "bound_claims_type": "glob",
  "bound_claims": {"nomad_job_id": "sift-sms-assistant"},
  "user_claim": "nomad_job_id",
  "claim_mappings": {"nomad_namespace": "nomad_namespace", "nomad_job_id": "nomad_job_id"},
  "token_type": "service",
  "token_policies": "sift-sms-assistant",
  "token_period": "72h"
}
EOF

echo "Done. Secret at secret/sift-sms-assistant, policy+role 'sift-sms-assistant' created."
echo ""
echo "One more manual step - add this public key to eink.lan's"
echo "authorized_keys (RESET's SSH access won't work until you do):"
echo ""
echo "  ssh eink.lan \"echo '$(cat "$KEY_DIR/eink_reset_key.pub")' >> ~/.ssh/authorized_keys\""
echo ""
rm -rf "$KEY_DIR"
