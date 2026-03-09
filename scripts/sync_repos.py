import os
import json
import logging
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone
from github import Github, GithubException
import time

# --- Logging Setup -----------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

# --- Config ------------------------------------------------------------------

PERSONAL_TOKEN   = os.environ["PERSONAL_TOKEN"]
ORG_TOKEN        = os.environ["ORG_TOKEN"]
PERSONAL_USER    = os.environ["PERSONAL_USERNAME"]
ORG_NAME         = os.environ["ORG_NAME"]
EXCLUDE_REPOS    = set(
    r.strip() for r in os.getenv("EXCLUDE_REPOS", "").split(",") if r.strip()
)

# Also load exclusions from config/mirror-config.json if it exists
_config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mirror-config.json")
if os.path.exists(_config_path):
    with open(_config_path) as _f:
        _config = json.load(_f)
        EXCLUDE_REPOS.update(_config.get("exclude", []))

# --- Report Tracking ---------------------------------------------------------

report = {
    "run_timestamp": datetime.now(timezone.utc).isoformat(),
    "new_repos_created": [],
    "repos_updated": [],
    "repos_skipped": [],
    "repos_excluded": [],
    "errors": []
}

# --- GitHub Clients ----------------------------------------------------------

personal_gh = Github(PERSONAL_TOKEN)
org_gh      = Github(ORG_TOKEN)

def get_personal_repos():
    """Fetch all personal repos excluding forks if desired."""
    user = personal_gh.get_user(PERSONAL_USER)
    repos = []
    for repo in user.get_repos(type='owner'):
        if repo.name not in EXCLUDE_REPOS:
            repos.append(repo)
        else:
            log.info(f"Excluded repo: {repo.name}")
            report["repos_excluded"].append(repo.name)
    return repos

def get_org_repos():
    """Fetch all existing org repos as a name -> repo dict."""
    org = org_gh.get_organization(ORG_NAME)
    return {repo.name: repo for repo in org.get_repos()}

def create_org_repo(org, personal_repo):
    """Create a new repo in the org mirroring personal repo settings."""
    try:
        new_repo = org.create_repo(
            name=personal_repo.name,
            description=personal_repo.description or "",
            private=personal_repo.private,
            has_issues=personal_repo.has_issues,
            has_wiki=personal_repo.has_wiki,
            has_projects=personal_repo.has_projects,
            auto_init=False
        )
        log.info(f"Created org repo: {new_repo.name}")
        return new_repo
    except GithubException as e:
        log.error(f"Failed to create {personal_repo.name}: {e}")
        report["errors"].append({
            "repo": personal_repo.name,
            "action": "create",
            "error": str(e)
        })
        return None

def mirror_repo(personal_repo_url, org_repo_url, repo_name):
    """
    Mirror all branches, tags, and commits from personal -> org.
    Uses --mirror for full sync without duplicating history.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        log.info(f"Mirroring: {repo_name}")

        # Inject tokens into URLs for auth
        auth_personal_url = personal_repo_url.replace(
            "https://", f"https://{PERSONAL_TOKEN}@"
        )
        auth_org_url = org_repo_url.replace(
            "https://", f"https://{ORG_TOKEN}@"
        )

        # Clone mirror from personal
        result = subprocess.run(
            ["git", "clone", "--mirror", auth_personal_url, tmp_dir],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"Clone failed: {result.stderr}")

        # Push mirror to org
        result = subprocess.run(
            ["git", "remote", "set-url", "--push", "origin", auth_org_url],
            capture_output=True, text=True, cwd=tmp_dir, timeout=30
        )

        result = subprocess.run(
            ["git", "push", "--mirror"],
            capture_output=True, text=True, cwd=tmp_dir, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"Push failed: {result.stderr}")

        log.info(f"Mirror complete: {repo_name}")
        return True

    except Exception as e:
        log.error(f"Mirror failed for {repo_name}: {e}")
        report["errors"].append({
            "repo": repo_name,
            "action": "mirror",
            "error": str(e)
        })
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def has_new_commits(personal_repo, org_repo):
    """
    Check if personal repo has commits newer than the org repo's last push.
    Returns True if update is needed.
    """
    try:
        personal_pushed = personal_repo.pushed_at
        org_pushed      = org_repo.pushed_at

        if personal_pushed is None:
            return False  # Empty repo

        if org_pushed is None:
            return True   # Org repo exists but never had a push

        return personal_pushed > org_pushed

    except Exception as e:
        log.warning(f"Could not compare timestamps for {personal_repo.name}: {e}")
        return True  # Sync anyway if unsure

def update_repo_metadata(personal_repo, org_repo):
    """Sync description and visibility if changed."""
    try:
        needs_update = (
            personal_repo.description != org_repo.description or
            personal_repo.private != org_repo.private
        )
        if needs_update:
            org_repo.edit(
                description=personal_repo.description or "",
                private=personal_repo.private
            )
            log.info(f"Updated metadata for: {org_repo.name}")
    except GithubException as e:
        log.warning(f"Could not update metadata for {org_repo.name}: {e}")

# --- Main Sync Logic ---------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info(f"Starting sync: {PERSONAL_USER} -> {ORG_NAME}")
    log.info("=" * 60)

    org = org_gh.get_organization(ORG_NAME)

    personal_repos = get_personal_repos()
    org_repos_map  = get_org_repos()

    log.info(f"Personal repos found: {len(personal_repos)}")
    log.info(f"Org repos existing:   {len(org_repos_map)}")

    for personal_repo in personal_repos:
        repo_name = personal_repo.name

        try:
            # Skip empty repos
            if personal_repo.size == 0 and personal_repo.pushed_at is None:
                log.info(f"Skipping empty repo: {repo_name}")
                report["repos_skipped"].append({
                    "repo": repo_name,
                    "reason": "empty repository"
                })
                continue

            # NEW REPO: doesn't exist in org
            if repo_name not in org_repos_map:
                log.info(f"New repo detected: {repo_name}")
                org_repo = create_org_repo(org, personal_repo)

                if org_repo:
                    success = mirror_repo(
                        personal_repo.clone_url,
                        org_repo.clone_url,
                        repo_name
                    )
                    if success:
                        report["new_repos_created"].append(repo_name)

            # EXISTING REPO: check for updates
            else:
                org_repo = org_repos_map[repo_name]

                if has_new_commits(personal_repo, org_repo):
                    log.info(f"Update needed: {repo_name}")
                    success = mirror_repo(
                        personal_repo.clone_url,
                        org_repo.clone_url,
                        repo_name
                    )
                    if success:
                        update_repo_metadata(personal_repo, org_repo)
                        report["repos_updated"].append(repo_name)
                else:
                    log.info(f"Up to date, skipping: {repo_name}")
                    report["repos_skipped"].append({
                        "repo": repo_name,
                        "reason": "no new commits"
                    })

        except Exception as e:
            log.error(f"Unexpected error processing {repo_name}, skipping: {e}")
            report["errors"].append({
                "repo": repo_name,
                "action": "process",
                "error": str(e)
            })

        # Rate limit protection
        time.sleep(1)

    # Final Report
    log.info("\n" + "=" * 60)
    log.info("SYNC COMPLETE - SUMMARY")
    log.info("=" * 60)
    log.info(f"New repos created : {len(report['new_repos_created'])}")
    log.info(f"Repos updated     : {len(report['repos_updated'])}")
    log.info(f"Repos skipped     : {len(report['repos_skipped'])}")
    log.info(f"Repos excluded    : {len(report['repos_excluded'])}")
    log.info(f"Errors            : {len(report['errors'])}")

    if report["errors"]:
        log.error("Errors encountered:")
        for err in report["errors"]:
            log.error(f"  - {err}")

    # Save report artifact
    with open("sync_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    log.info("Report saved: sync_report.json")

    if report["errors"]:
        log.warning(f"{len(report['errors'])} repo(s) had errors — see report for details")

if __name__ == "__main__":
    main()
