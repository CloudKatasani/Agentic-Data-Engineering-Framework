#!/bin/bash
# EC2 user-data for DataCrew- BuildWithAI (Amazon Linux 2023).
# Installs Docker, fetches the code, writes /opt/adef/.env from SSM Parameter Store and starts the console.
#
# Secrets are NOT put in this script: user-data is readable in the EC2 console. Store them in SSM Parameter
# Store as SecureString under /adef/ and attach an instance role that allows ssm:GetParametersByPath on
# arn:aws:ssm:<region>:<account>:parameter/adef/* (see deploy/ec2/README.md).
#
# Read from /adef/ when present and written to /opt/adef/.env:
#   ADEF_API_TOKEN, ADEF_MASTER_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, AZURE_OPENAI_API_KEY,
#   AZURE_OPENAI_ENDPOINT, AWS_BEARER_TOKEN_BEDROCK, ORACLE_PASSWORD, DB2_PASSWORD, and any other ADEF_* setting.
# Read from /adef/ and used only to fetch the code (never written to .env):
#   GIT_TOKEN   a read-only token, needed only when the repository is private.
set -euo pipefail

# ---- edit these four lines if you need to ------------------------------------------------------------
REPO_URL="${REPO_URL:-https://github.com/CloudKatasani/Agentic-Data-Engineering-Framework-BuildWithAI.git}"
REPO_REF="${REPO_REF:-main}"    # a branch or a release tag
DOMAIN="${DOMAIN:-}"            # e.g. datacrew.example.com for automatic HTTPS (DNS A record must point here first)
PROFILES="${PROFILES:-}"        # "oracle", "db2" or "oracle db2" to also start synthetic source databases
# ------------------------------------------------------------------------------------------------------

exec > >(tee -a /var/log/adef-setup.log) 2>&1
echo "== DataCrew setup started $(date -u +%FT%TZ)"

dnf install -y docker git
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Region from the instance metadata service (IMDSv2)
IMDS_TOKEN="$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')"
REGION="$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/placement/region)"

# Secrets and settings from SSM. A missing role or an empty path is not fatal: the console then starts
# with a generated access token and the offline Demo Simulator.
PARAMS="$(aws ssm get-parameters-by-path --region "$REGION" --path /adef/ --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text 2>/dev/null || true)"
[ -n "$PARAMS" ] || echo "!! No parameters read from SSM path /adef/ (check the instance role). Continuing without them."
param() { printf '%s\n' "$PARAMS" | awk -F'\t' -v n="/adef/$1" '$1 == n { print $2 }'; }

# Fetch the code. A private repository needs /adef/GIT_TOKEN; the token is sent as a header and not stored.
if [ ! -d /opt/adef/.git ]; then
  GIT_TOKEN="$(param GIT_TOKEN)"
  if [ -n "$GIT_TOKEN" ]; then
    AUTH="$(printf 'x-access-token:%s' "$GIT_TOKEN" | base64 -w0)"
    git -c http.extraheader="Authorization: Basic $AUTH" clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /opt/adef
  else
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /opt/adef
  fi
fi
cd /opt/adef
umask 077

# Keep a previously generated access token and vault key if this script runs again, so that saved keys stay readable.
OLD_TOKEN="$(grep -s '^ADEF_API_TOKEN=' .env | cut -d= -f2- || true)"
OLD_KEY="$(grep -s '^ADEF_MASTER_KEY=' .env | cut -d= -f2- || true)"
: > .env
printf '%s\n' "$PARAMS" | while IFS=$'\t' read -r name value; do
  if [ -n "$name" ] && [ "${name##*/}" != "GIT_TOKEN" ]; then echo "${name##*/}=${value}" >> .env; fi
done
grep -q '^ADEF_API_TOKEN=' .env || echo "ADEF_API_TOKEN=${OLD_TOKEN:-$(openssl rand -hex 24)}" >> .env
grep -q '^ADEF_MASTER_KEY=' .env || echo "ADEF_MASTER_KEY=${OLD_KEY:-$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')}" >> .env
grep -q '^AWS_REGION=' .env || echo "AWS_REGION=$REGION" >> .env
if [ -n "$DOMAIN" ]; then echo "DOMAIN=$DOMAIN" >> .env; fi
chmod 600 .env

ARGS=()
for p in $PROFILES; do ARGS+=(--profile "$p"); done
if [ -n "$DOMAIN" ]; then ARGS+=(--profile https); fi
docker compose "${ARGS[@]}" up -d --build

# Wait for the console to answer, so the log says clearly whether the start worked.
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    if [ -n "$DOMAIN" ]; then URL="https://$DOMAIN"; else URL="http://<public-ip>:8000"; fi
    echo "== DataCrew is running. Open $URL"
    echo "== Access token: read /adef/ADEF_API_TOKEN from SSM, or run: sudo grep ADEF_API_TOKEN /opt/adef/.env"
    exit 0
  fi
  sleep 5
done
echo "!! The console did not answer within 5 minutes. Check: cd /opt/adef && sudo docker compose ps && sudo docker compose logs adef"
exit 1
