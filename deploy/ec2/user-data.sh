#!/bin/bash
# EC2 user-data for ADEF (Amazon Linux 2023). Installs Docker, fetches ADEF, starts it with HTTPS optional.
#
# Secrets are NOT put in this script (user-data is readable in the EC2 console). Store them in SSM
# Parameter Store as SecureString under /adef/ and attach an instance role allowing
# ssm:GetParametersByPath on arn:aws:ssm:<region>:<account>:parameter/adef/* (plus kms:Decrypt):
#   aws ssm put-parameter --name /adef/ANTHROPIC_API_KEY --type SecureString --value '<key>'
#   aws ssm put-parameter --name /adef/ADEF_API_TOKEN   --type SecureString --value "$(openssl rand -hex 24)"
# Any of ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, AZURE_OPENAI_API_KEY, AWS_BEARER_TOKEN_BEDROCK,
# ADEF_API_TOKEN, ADEF_MASTER_KEY, ORACLE_PASSWORD, DB2_PASSWORD found under /adef/ are written to /opt/adef/.env.
set -euo pipefail
REPO_URL="${REPO_URL:-https://github.com/CloudKatasani/Agentic-Data-Engineering-Framework.git}"
REPO_REF="${REPO_REF:-main}"
DOMAIN="${DOMAIN:-}"            # set for automatic HTTPS (DNS A record must point at this instance)
PROFILES="${PROFILES:-}"        # e.g. "oracle" or "oracle db2" to start synthetic source databases

dnf install -y docker git
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

if [ ! -d /opt/adef/.git ]; then git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /opt/adef; fi
cd /opt/adef
umask 077
REGION="$(TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') \
  && curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)"
: > .env
aws ssm get-parameters-by-path --region "$REGION" --path /adef/ --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text | while IFS=$'\t' read -r name value; do
    echo "${name##*/}=${value}" >> .env
  done
grep -q '^ADEF_API_TOKEN=' .env || echo "ADEF_API_TOKEN=$(openssl rand -hex 24)" >> .env
grep -q '^ADEF_MASTER_KEY=' .env || echo "ADEF_MASTER_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" >> .env
[ -n "$DOMAIN" ] && echo "DOMAIN=$DOMAIN" >> .env
chmod 600 .env

ARGS=()
for p in $PROFILES; do ARGS+=(--profile "$p"); done
[ -n "$DOMAIN" ] && ARGS+=(--profile https)
docker compose "${ARGS[@]}" up -d --build
echo "ADEF is starting. Token: sudo grep ADEF_API_TOKEN /opt/adef/.env (or read /adef/ADEF_API_TOKEN from SSM)."
