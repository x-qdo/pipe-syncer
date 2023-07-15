import io
import argparse
from itertools import chain

from apply import CustomApply
from config import log_level, tag_prefix, config, sync_branch_prefix
from utils import get_latest_semver_tag, find_nearest_common_tag, apply_replacements_to_patch
from git import Repo, GitCommandError
import semver
import logging

# Set up logging
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="Sync repositories")
parser.add_argument("from_repo", help="The source repository name")
parser.add_argument("to_repo", help="The target repository name")
parser.add_argument("--range", help="Specific commit range in format 'start_commit..end_commit'", default="")
parser.add_argument("--interactive", "-i", action=argparse.BooleanOptionalAction)
args = parser.parse_args()

source_repo_name = args.from_repo
target_repo_name = args.to_repo

if source_repo_name not in config["repos"] or target_repo_name not in config["repos"]:
    logger.error("Invalid repository names provided. Please check the configuration.")
    exit(1)

source_repo_config = config["repos"][source_repo_name]
target_repo_config = config["repos"][target_repo_name]

source_repo = Repo(source_repo_config["path"])
target_repo = Repo(target_repo_config["path"])
custom_apply = CustomApply(target_repo, interactive=args.interactive)

if args.range:
    logger.debug("Using specified commit range: {}".format(args.range))
    commits_to_apply = source_repo.git.log(args.range, "--pretty=format:%H").split()
else:
    source_latest_tag = get_latest_semver_tag(source_repo, tag_prefix)
    target_latest_tag = get_latest_semver_tag(target_repo, tag_prefix)

    if not source_latest_tag and not target_latest_tag:
        logger.error("No semver tags found in both repositories")
        exit(1)

    if not source_latest_tag or (target_latest_tag and semver.compare(source_latest_tag.name[len(tag_prefix):],
                                                                      target_latest_tag.name[len(tag_prefix):]) < 0):
        # Sync from target to source
        logger.error("Syncing from target is newer than source, please check your config. "
                     "Source latest: %s Target latest: %s" % (source_latest_tag, target_latest_tag))
        exit(1)

    # Get every commit from the source repo since the latest synced tag
    common_tag = find_nearest_common_tag(source_repo, target_repo, tag_prefix)
    logger.debug(
        "Getting commits to apply since the "
        "latest synced tag: %s till: %s" % (common_tag.name, source_latest_tag.name)
    )
    commits_to_apply = source_repo.git.log(f"{common_tag.commit.hexsha}..{source_latest_tag.commit.hexsha}",
                                           "--pretty=format:%H").split()

if len(commits_to_apply) < 1:
    exit(0)

latest_commit_to_apply = commits_to_apply[-1]
source_short_hash = source_repo.git.rev_parse(latest_commit_to_apply, short=True)
SYNC_BRANCH_NAME = f"{sync_branch_prefix}-{source_short_hash}"
try:
    sync_branch = target_repo.create_head(SYNC_BRANCH_NAME)
except GitCommandError:
    sync_branch = target_repo.heads[SYNC_BRANCH_NAME]

target_repo.head.reference = sync_branch
applied_commits = {
    commit.message.split("Original commit: ")[-1].strip()
    for commit in chain([sync_branch.commit], sync_branch.commit.iter_parents())
    if "Original commit: " in commit.message
}

# Reapply the commits
for commit_hash in reversed(commits_to_apply):
    if commit_hash in applied_commits:
        logger.info(f"Commit {commit_hash} already applied, skipping")
        continue

    commit = source_repo.commit(commit_hash)
    short_message = (commit.message[:75] + '..') if len(commit.message) > 75 else commit.message
    logger.info(f"Applying commit [{commit_hash}]:\n{short_message}")

    if args.interactive:
        user_input = input("Apply? [Y/n/s]: ")
        if user_input == 'n':
            exit(0)
        elif user_input == 's':
            logger.info("Skip applying")
            continue

    diff = commit.parents[0].diff(commit, create_patch=True, ignore_cr_at_eol=True, unified=5)
    # Apply the diff using the CustomApply class
    if custom_apply.apply(diff):
        logger.info(f"Applied commit {commit_hash} to target repo")
        original_message = commit.message.strip()
        updated_message = f"{original_message}\n\nOriginal commit: {commit_hash}"
        target_repo.git.add(".")
        target_repo.git.commit("-m", updated_message)
    else:
        logger.error(f"Can't apply commit {commit_hash} to target repo")
