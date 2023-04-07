import io
import os
import tempfile

from config import log_level, source_repo_path, target_repo_path, tag_prefix
from utils import get_latest_semver_tag
from git import Repo, GitCommandError
import semver
import logging

# Set up logging
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

source_repo = Repo(source_repo_path)
target_repo = Repo(target_repo_path)
logger.debug("Getting latest semver tags from both repositories")
source_latest_tag = get_latest_semver_tag(source_repo, tag_prefix)
target_latest_tag = get_latest_semver_tag(target_repo, tag_prefix)

if not source_latest_tag and not target_latest_tag:
    logger.error("No semver tags found in both repositories")
    exit(1)

if not source_latest_tag or (target_latest_tag and semver.compare(source_latest_tag.name[len(tag_prefix):],
                                                                  target_latest_tag.name[len(tag_prefix):]) < 0):
    # Sync from target to source
    logger.debug("Syncing from target to source")
    source_repo, target_repo = target_repo, source_repo
    source_latest_tag, target_latest_tag = target_latest_tag, source_latest_tag

# TODO: add commit search between target_latest_tag and source_latest_tag in source_repo
#       we should copy commits from  target_latest_tag..source_latest_tag.
#       For that we need to find same tag by name in source_repo using separate function

# Get every commit from the source repo since the latest synced tag
logger.debug("Getting commits to apply since the latest synced tag")

# TODO: Update fetching list of commits using two tags found in source_repo
commits_to_apply = source_repo.git.log(f"{source_latest_tag.commit.hexsha}..HEAD", "--pretty=format:%H").split()

# Reapply the commits
for commit_hash in reversed(commits_to_apply):
    logger.debug(f"Applying commit {commit_hash}")
    commit = source_repo.commit(commit_hash)

    stream = io.BytesIO()
    patch = source_repo.git.format_patch(
        "--no-stat", "--no-numbered", "--stdout", "--no-attach", "-k", "-1",
        str(commit.hexsha), output_stream=stream
    )
    with open("patch.txt", "wb") as f:
        f.write(stream.getbuffer())
    # Create a patch excluding the specified folders
    # filtered_diff = create_patch(commit, ignore_folders)
    # Check if the patch has already been applied
    try:
        with open("patch.txt", "rb") as f:
            # TODO: Read ignore_folders from config
            (status, stdout, stderr) = target_repo.git.apply(
                "--3way", "--check",
                "--exclude=.helm/*",
                "--exclude=src/com/pipeline/data/*",
                "--exclude=test/*",
                "--exclude=Jenkinsfile",
                "--exclude=.sops.yaml",
                "--exclude=vars/globalEnv.groovy",
                "--exclude=test/*",
                "-v",
                "--unidiff-zero",
                "--recount",
                istream=f,
                with_extended_output=True, with_exceptions=False
            )

        # Reopen file to reset a pointer for stdin stream
        with open("patch.txt", "rb") as f:
            if status == 0:
                logger.info(f"Possible to apply commit {commit_hash} to target repo")
                # Apply the patch
                (status, stdout, stderr) = target_repo.git.apply(
                    "--3way",
                    "--exclude=.helm/*",
                    "--exclude=src/com/pipeline/data/*",
                    "--exclude=test/*",
                    "--exclude=Jenkinsfile",
                    "--exclude=.sops.yaml",
                    "--exclude=vars/globalEnv.groovy",
                    "--exclude=test/*",
                    "-v",
                    "--unidiff-zero",
                    "--recount",
                    istream=f,
                    with_extended_output=True,
                    with_exceptions=False
                )
                logger.info(f"Applied commit {commit_hash} to target repo: %s\n\n%s" % (stdout, stderr))
                original_message = commit.message.strip()
                updated_message = f"{original_message}\n\nOriginal commit: {commit_hash}"
                target_repo.git.commit("-m", updated_message)
                # TODO: Move tag to the new commit to make sure that we can calculate the diff next time

            else:
                logger.error(f"Can't apply commit {commit_hash} to target repo: %s" % stderr)

    except GitCommandError as e:
        logger.error(f"Failed to apply commit {commit_hash}: {e}")
        continue
