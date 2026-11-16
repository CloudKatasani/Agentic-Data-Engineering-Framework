# Host DataCrew- BuildWithAI on an AWS EC2 instance

About 20 minutes from an AWS account to a running console. You end up with one EC2 instance
running the console in Docker, model keys held in SSM Parameter Store (never on your laptop
or in the launch script), and access limited to your IP address or to HTTPS on your domain.

There are two ways to do the same steps: the **AWS command line** (copy and paste, section A)
or the **AWS console** (clicks, section B). Both use `deploy/ec2/user-data.sh`, which installs
Docker, fetches the code, reads your secrets from Parameter Store and starts the console.

> These steps were written and syntax-checked but not run against a live AWS account in the
> session that produced them. If a step fails, section 7 (Troubleshooting) says where to look.

## Before you start

| You need | Notes |
|---|---|
| An AWS account and a region | The examples use `us-east-1`; any region works |
| Permission to create an IAM role, a security group, SSM parameters and an EC2 instance | An administrator, or a role with those rights |
| At least one model key | For example an Anthropic key. Without one the console still runs, on the offline Demo Simulator |
| For section A: AWS CLI v2, signed in (`aws sts get-caller-identity` works) | And this repository cloned on your machine |
| Optional: a domain name you control | Only for HTTPS (step 6) |
| If this repository is private: a read-only Git token | Stored as `/adef/GIT_TOKEN` in step 1 |

**What it costs.** One `t3.large` instance (2 vCPU, 8 GB) with 30 GB of storage, roughly
USD 65 to 75 a month if left running, plus model usage billed by your model provider. Stop
the instance when you are not demonstrating (step 8) and you pay only for storage.

---

## A. Command line

Run these on your own machine, from the root of the repository.

### 1. Store the secrets in Parameter Store

```bash
export AWS_REGION=us-east-1
```

```bash
aws ssm put-parameter --name /adef/ADEF_API_TOKEN --type SecureString --value "$(openssl rand -hex 24)"
```

```bash
aws ssm put-parameter --name /adef/ANTHROPIC_API_KEY --type SecureString --value '<your key>'
```

- `ADEF_API_TOKEN` is the password the console asks for. Read it back later with the command
  in step 5.
- Add any other key the same way, using its name: `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT`, `AWS_BEARER_TOKEN_BEDROCK`. The agent team
  is chosen from the keys that are present.
- Optional settings go in the same place: `ADEF_BRAND_NAME`, `ADEF_MODEL_TIMEOUT_SECONDS`,
  `ORACLE_PASSWORD`, `DB2_PASSWORD`.
- Private repository only: `aws ssm put-parameter --name /adef/GIT_TOKEN --type SecureString --value '<read-only token>'`.

### 2. Create the instance role

The instance needs permission to read those parameters, and nothing else.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

```bash
aws iam create-role --role-name datacrew-ec2 --assume-role-policy-document file://deploy/ec2/trust-policy.json
```

```bash
sed -e "s/REGION/$AWS_REGION/g" -e "s/ACCOUNT_ID/$ACCOUNT_ID/g" deploy/ec2/parameter-policy.json > /tmp/datacrew-policy.json
```

```bash
aws iam put-role-policy --role-name datacrew-ec2 --policy-name read-datacrew-parameters --policy-document file:///tmp/datacrew-policy.json
```

```bash
aws iam attach-role-policy --role-name datacrew-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
```

```bash
aws iam create-instance-profile --instance-profile-name datacrew-ec2
```

```bash
aws iam add-role-to-instance-profile --instance-profile-name datacrew-ec2 --role-name datacrew-ec2
```

`AmazonSSMManagedInstanceCore` lets you open a shell with Session Manager, so the instance
needs no SSH key and no open SSH port.

### 3. Create the security group

Opens port 8000 to **your current IP address only**.

```bash
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
```

```bash
SG_ID=$(aws ec2 create-security-group --group-name datacrew --description "DataCrew console" --vpc-id "$VPC_ID" --query GroupId --output text)
```

```bash
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8000 --cidr "$(curl -s https://checkip.amazonaws.com)/32"
```

Never open port 8000 to `0.0.0.0/0`. For a client audience use HTTPS (step 6).

### 4. Launch the instance

```bash
AMI_ID=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
```

```bash
INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type t3.large \
  --iam-instance-profile Name=datacrew-ec2 --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3","Encrypted":true}}]' \
  --metadata-options HttpTokens=required \
  --user-data file://deploy/ec2/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=datacrew}]' \
  --query 'Instances[0].InstanceId' --output text)
```

If `run-instances` says the instance profile is invalid, wait 15 seconds and run it again:
a new role takes a moment to become usable.

### 5. Open the console

Setup takes 4 to 8 minutes after launch (it builds the container image).

```bash
aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID"
```

```bash
aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
```

```bash
aws ssm get-parameter --name /adef/ADEF_API_TOKEN --with-decryption --query Parameter.Value --output text
```

Open `http://<public-ip>:8000` and paste the token when asked. Then go to
**Guardrails → Run suite**: 18 of 18 scenarios should pass.

To avoid opening any port at all, forward the port through Session Manager instead and open
`http://localhost:8000`:

```bash
aws ssm start-session --target "$INSTANCE_ID" --document-name AWS-StartPortForwardingSession --parameters portNumber=8000,localPortNumber=8000
```

---

## B. AWS console (no command line)

1. **Systems Manager → Parameter Store → Create parameter.** Create `/adef/ADEF_API_TOKEN`
   (type *SecureString*, value: a long random string) and `/adef/ANTHROPIC_API_KEY`
   (*SecureString*, your key). Add other keys the same way (see step A1).
2. **IAM → Roles → Create role.** Trusted entity: *AWS service*, use case *EC2*. Attach
   `AmazonSSMManagedInstanceCore`. Name it `datacrew-ec2`. Open the role, **Add permissions →
   Create inline policy → JSON**, paste `deploy/ec2/parameter-policy.json` with `REGION` and
   `ACCOUNT_ID` replaced, and save.
3. **EC2 → Launch instance.**
   - Name: `datacrew`. AMI: **Amazon Linux 2023** (64-bit x86). Type: **t3.large**.
   - Key pair: *Proceed without a key pair* (Session Manager is used instead).
   - Network settings → Edit: create a security group with one inbound rule,
     **Custom TCP, port 8000, source My IP**.
   - Storage: **30 GiB gp3**, encrypted.
   - Advanced details → IAM instance profile: **datacrew-ec2**.
   - Advanced details → Metadata version: **V2 only (token required)**.
   - Advanced details → User data: paste the whole of `deploy/ec2/user-data.sh`.
   - Launch.
4. Wait 4 to 8 minutes. Copy the instance's **Public IPv4 address**, open
   `http://<public-ip>:8000`, and paste the value of `/adef/ADEF_API_TOKEN`.

---

## 6. HTTPS on your own domain (recommended for a client audience)

1. Give the instance a fixed address: **EC2 → Elastic IPs → Allocate**, then **Associate** it
   with the instance.
2. In your DNS, create an **A record** for the name you want (for example
   `datacrew.example.com`) pointing at that address. Wait until it resolves.
3. Open ports **80 and 443** to the audience in the security group, and remove the port 8000
   rule.
4. Before launching, set `DOMAIN` near the top of `user-data.sh`:

   ```bash
   DOMAIN="${DOMAIN:-datacrew.example.com}"
   ```

   On an instance that is already running, open a shell (step 7) and run:

   ```bash
   cd /opt/adef && echo "DOMAIN=datacrew.example.com" | sudo tee -a .env && sudo docker compose --profile https up -d
   ```

The certificate is issued automatically on first request. The console is then at
`https://datacrew.example.com`. The access token is still required.

## 7. Day-to-day operation

**Open a shell on the instance** (no SSH key needed):

```bash
aws ssm start-session --target "$INSTANCE_ID"
```

**See what happened during setup, or why the console is not answering:**

```bash
sudo tail -n 50 /var/log/adef-setup.log
```

```bash
cd /opt/adef && sudo docker compose ps && sudo docker compose logs --tail 80 adef
```

**Add or change a model key:** update the parameter (add `--overwrite`), then refresh the
instance's settings and restart:

```bash
aws ssm put-parameter --name /adef/OPENAI_API_KEY --type SecureString --value '<your key>' --overwrite
```

```bash
sudo bash /opt/adef/deploy/ec2/user-data.sh
```

Re-running the script keeps the existing access token and vault key, so keys saved in the
console stay readable.

**Update to the latest version:**

```bash
cd /opt/adef && sudo git pull && sudo docker compose up -d --build
```

If the repository is private, `git pull` on the instance has no credentials. Either make a
new instance from the updated code, or pull with a token for that one command:

```bash
cd /opt/adef && sudo git -c http.extraheader="Authorization: Basic $(printf 'x-access-token:%s' "$(aws ssm get-parameter --name /adef/GIT_TOKEN --with-decryption --query Parameter.Value --output text)" | base64 -w0)" pull && sudo docker compose up -d --build
```

**Back up the data.** Runs, settings, the encrypted vault and run archives live in the Docker
volume `adef_adef-data` on the instance's disk. Take an EBS snapshot of the volume (EC2 →
Volumes → Actions → Create snapshot) before an update and on a schedule that suits you. Old
run archives are not removed automatically.

**Troubleshooting.**

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser cannot reach port 8000 | Your IP address changed, or setup is still running | Update the security group rule to your current IP; wait and check the setup log |
| Setup log says "No parameters read from SSM" | Instance profile missing, or the policy has the wrong region or account | Attach `datacrew-ec2`; check `parameter-policy.json`; re-run the script |
| Setup log stops at `git clone` | Private repository | Store `/adef/GIT_TOKEN` and re-run the script |
| Console asks for a token and rejects it | Wrong value | Read `/adef/ADEF_API_TOKEN` again; if you never stored one, run `sudo grep ADEF_API_TOKEN /opt/adef/.env` |
| Agents show "no key - simulated" | The key is not in Parameter Store, or the instance was not refreshed | Store the key and re-run the script |
| HTTPS certificate is not issued | DNS does not point at the instance yet, or ports 80 and 443 are closed | Fix DNS and the security group, then `sudo docker compose --profile https restart caddy` |

## 8. Stop paying, or remove everything

Stop the instance between demonstrations (data is kept; you pay only for storage):

```bash
aws ec2 stop-instances --instance-ids "$INSTANCE_ID"
```

```bash
aws ec2 start-instances --instance-ids "$INSTANCE_ID"
```

The public IP address changes on restart unless you attached an Elastic IP.

Remove everything:

```bash
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"
```

```bash
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" && aws ec2 delete-security-group --group-id "$SG_ID"
```

```bash
aws iam remove-role-from-instance-profile --instance-profile-name datacrew-ec2 --role-name datacrew-ec2 && aws iam delete-instance-profile --instance-profile-name datacrew-ec2
```

```bash
aws iam delete-role-policy --role-name datacrew-ec2 --policy-name read-datacrew-parameters && aws iam detach-role-policy --role-name datacrew-ec2 --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore && aws iam delete-role --role-name datacrew-ec2
```

```bash
aws ssm delete-parameters --names /adef/ADEF_API_TOKEN /adef/ANTHROPIC_API_KEY
```

Terminating the instance deletes its disk and all run data. Take a snapshot first if you
want to keep it.

## Optional extras

**Synthetic Oracle or Db2 source database on the same instance.** Use `t3.xlarge` and 60 GB of
storage, store `/adef/ORACLE_PASSWORD` (or `/adef/DB2_PASSWORD`), and set `PROFILES="oracle"`
near the top of `user-data.sh` before launching. Then seed it and add the connection:

```bash
cd /opt/adef && sudo docker compose exec adef python -m adef source-db seed --type oracle --dsn oracle:1521/FREEPDB1 --user system --domain telco --password-env ORACLE_PASSWORD
```

In the console: **Integrations → Source databases → Add a connection** (DSN
`oracle:1521/FREEPDB1`, user `system`).

**A release tag or your own fork.** Set `REPO_REF` or `REPO_URL` near the top of `user-data.sh`.

**Without Docker.** Copy the repository to `/opt/adef`, create a user `adef`, put the settings
in `/opt/adef/.env` (`chmod 600`, same names as `.env.example`), then install
`deploy/systemd/adef.service`. `run.sh` creates the Python environment on first start.

## Security notes

- Keys live in Parameter Store and in `/opt/adef/.env` on the instance (readable by root only).
  They are never in the launch script, the repository or the browser.
- The console is protected by one shared access token. Treat it like a password, and prefer
  HTTPS or Session Manager port forwarding to plain HTTP.
- The instance needs outbound internet access to reach your model providers, GitHub and the
  container registry. It needs no inbound access other than the console port.
- This is a single-instance setup for demonstrations and pilots. It has no automatic backup
  and no high availability.
