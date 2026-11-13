# Run ADEF on AWS EC2

About 10 minutes from an empty account to a running console with live agents.

## 1. Store secrets in SSM Parameter Store (once)

Never put keys in user-data: it is readable in the EC2 console.

```bash
aws ssm put-parameter --name /adef/ANTHROPIC_API_KEY --type SecureString --value '<your key>'
```

```bash
aws ssm put-parameter --name /adef/ADEF_API_TOKEN --type SecureString --value "$(openssl rand -hex 24)"
```

Add any of `OPENAI_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`,
`ORACLE_PASSWORD`, `DB2_PASSWORD` the same way. The agent team is chosen from the keys present.

## 2. Instance role

Create a role for EC2 with this policy (replace region and account):

```json
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["ssm:GetParametersByPath"], "Resource": "arn:aws:ssm:REGION:ACCOUNT:parameter/adef/*"},
  {"Effect": "Allow", "Action": ["kms:Decrypt"], "Resource": "*", "Condition": {"StringEquals": {"kms:ViaService": "ssm.REGION.amazonaws.com"}}}]}
```

Attach `AmazonSSMManagedInstanceCore` as well, so you can open a shell with Session Manager instead of SSH.

## 3. Launch

- AMI: Amazon Linux 2023, instance type `t3.large` (8 GB). Use `t3.xlarge` if you add the Oracle or Db2 profiles.
- Storage: 30 GB gp3. Use 60 GB with Oracle or Db2.
- Security group: allow 443 (and 80, for certificate issuance) when using HTTPS, or 8000 from **your IP only**.
- Advanced details → IAM instance profile: the role above.
- User data: paste `deploy/ec2/user-data.sh`. Optional variables at the top:
  - `DOMAIN=adef.example.com` for automatic HTTPS (point a DNS A record at the instance first).
  - `PROFILES="oracle"` (or `"db2"`, or both) to start synthetic source databases.
  - `REPO_URL` / `REPO_REF` for your fork or a release tag.

## 4. Open the console

- With `DOMAIN`: `https://adef.example.com`.
- Without: `http://<public-ip>:8000`. Prefer an SSM port forward over opening the port:

  ```bash
  aws ssm start-session --target <instance-id> --document-name AWS-StartPortForwardingSession --parameters portNumber=8000,localPortNumber=8000
  ```

The console asks for the access token (`/adef/ADEF_API_TOKEN`).

## 5. Optional: seed and connect a source database

With `PROFILES="oracle"`, open a shell on the instance (Session Manager), then:

```bash
cd /opt/adef && sudo docker compose exec adef python -m adef source-db seed --type oracle --dsn oracle:1521/FREEPDB1 --user system --domain telco --password-env ORACLE_PASSWORD
```

Then in the console, **Jira & metadata → Source databases → Add a connection** (DSN `oracle:1521/FREEPDB1`,
user `system`). New runs can use it as the source for Pipeline 1.

## Updating

```bash
cd /opt/adef && sudo git pull && sudo docker compose up -d --build
```

## Without Docker

Copy the repository to `/opt/adef`, create a user `adef`, put secrets in `/opt/adef/.env` (`chmod 600`,
same variables as `.env.example`), then install `deploy/systemd/adef.service`. `run.sh` creates the
virtual environment on first start.
