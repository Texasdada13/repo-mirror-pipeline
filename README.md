# Repo Mirror Pipeline

Automated weekly pipeline that syncs repositories from a personal GitHub account
to the Patriot Tech Systems organization. Handles both new repos and updates to
existing repos.

## Schedule
- **Automatic:** Every Friday at 8:00 PM EST (Saturday 1:00 AM UTC)
- **Manual:** Trigger anytime via the Actions tab (workflow_dispatch)

## How It Works
1. Fetches all owned repos from the personal account
2. Fetches all existing repos from the org
3. For each personal repo:
   - **Excluded?** Skip and log it
   - **Empty?** Skip and log it
   - **New (not in org)?** Create in org + mirror all branches/tags
   - **Exists in org?** Compare `pushed_at` timestamps; mirror only if personal has newer commits
4. Syncs repo metadata (description, visibility) on update
5. Generates a JSON sync report artifact

## Sync Decision Logic
```
Personal Repo Found
       |
       v
Exists in EXCLUDE list? --YES--> Skip (log it)
       | NO
       v
Is repo empty? --YES--> Skip (log it)
       | NO
       v
Exists in Org? --NO--> Create new + Mirror
       | YES
       v
personal.pushed_at > org.pushed_at?
  YES --> Mirror updates (--mirror git push)
  NO  --> Skip (already up to date)
```

## File Structure
```
repo-mirror-pipeline/
  .github/
    workflows/
      sync-to-org.yml       # Full sync workflow (new + updates)
      mirror-repos.yml      # Legacy new-repo-only workflow
  scripts/
    sync_repos.py           # Python sync engine
  config/
    mirror-config.json      # Exclusion list
```

## Secrets Required
| Secret Name | Description |
|---|---|
| `PERSONAL_GITHUB_TOKEN` | PAT with `repo` read access + `read:user` |
| `ORG_GITHUB_TOKEN` | PAT with `repo` full access + `admin:org` write + `workflow` |
| `PERSONAL_USERNAME` | Your GitHub username |
| `ORG_NAME` | Target organization name |
| `EXCLUDE_REPOS` | Comma-separated repo names to skip (optional) |

## Configuration
- Edit `config/mirror-config.json` to permanently exclude specific repos
- Set `EXCLUDE_REPOS` secret for dynamic exclusions