# 🔄 New Repo Mirror Pipeline

Automated weekly pipeline that detects new repositories in the personal GitHub
account and mirrors them to the Patriot Tech Systems organization. Repos that
already exist in the org are skipped.

## Schedule
- **Automatic:** Every Friday at 8:00 PM EST
- **Manual:** Trigger anytime via the Actions tab

## How It Works
1. Fetches all repos from the personal account
2. Fetches all repos from the org
3. Compares the two lists
4. Mirrors only repos that exist in personal but NOT in org

## Manual Trigger Options
1. Go to the **Actions** tab → select **🔄 Weekly New Repo Mirror**
2. Click **Run workflow**
3. Options:
   - **Dry run:** Preview what would be mirrored without taking action
   - **Force sync:** Enter a repo name to re-mirror it even if it already exists in the org

## Configuration
- Edit `config/mirror-config.json` to permanently exclude specific repos

## Secrets Required
- `MIRROR_PAT` — GitHub Personal Access Token with repo + admin access