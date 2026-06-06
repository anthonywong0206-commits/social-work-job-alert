# Hong Kong Social Work Job Alert

GitHub Actions automation for searching Hong Kong social work / SWA jobs and sending a Telegram alert.

Schedule: Monday to Friday, 18:00 Hong Kong time.

## GitHub Secrets

Add these repository secrets before enabling the workflow:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Manual Test In GitHub

Open the repository Actions tab, choose **Hong Kong Social Work Job Search**, then run **workflow_dispatch**.

## Local Test

```powershell
$env:TELEGRAM_BOT_TOKEN="your-token"
$env:TELEGRAM_CHAT_ID="1209743522"
pip install -r requirements.txt
python job_search.py
```

Use this dry run command to print without sending Telegram:

```powershell
$env:DRY_RUN="1"
python job_search.py
```
