import io
import os
import re
from collections import defaultdict

import semver


def get_file_changes(patch):
    file_changes = defaultdict(list)
    current_file = None
    for line in patch.split("\n"):
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            current_file = line[6:]
        elif line.startswith("+") or line.startswith("-"):
            file_changes[current_file].append(line)
    return file_changes


def get_sorted_tags(repo, tag_prefix):
    tags = [tag for tag in repo.tags if tag.name.startswith(tag_prefix)]
    return sorted(tags, key=lambda tag: semver.parse_version_info(tag.name[len(tag_prefix):]))


def find_nearest_common_tag(source_repo, target_repo, tag_prefix):
    source_tags = get_sorted_tags(source_repo, tag_prefix)
    target_tags = get_sorted_tags(target_repo, tag_prefix)

    common_tags = [tag for tag in source_tags if tag in target_tags]
    if not common_tags:
        return None

    return common_tags[-1]


def get_latest_semver_tag(repo, prefix):
    tags = [tag for tag in repo.tags if tag.name.startswith(prefix)]
    if not tags:
        return None
    tags.sort(key=lambda t: semver.VersionInfo.parse(t.name[len(prefix):]), reverse=True)
    return tags[0]


def get_current_files(repo_root, ignore_folders):
    def get_lines(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().splitlines()

    current_files = {}
    for root, _, files in os.walk(repo_root):
        for f in files:
            file_path = os.path.relpath(os.path.join(root, f), repo_root)
            if any(file_path.startswith(folder) for folder in ignore_folders):
                continue
            current_files[file_path] = get_lines(os.path.join(root, f))

    return current_files


def move_tag(repo, tag_name, new_commit):
    try:
        tag = repo.tags[tag_name]
        repo.delete_tag(tag)
    except IndexError:
        pass  # The tag does not exist, we will create it

    repo.create_tag(tag_name, ref=new_commit, force=True)


def generate_exclude_args(ignore_folders):
    exclude_args = []
    for folder in ignore_folders:
        if folder.endswith('/'):
            folder = f"{folder}*"
        exclude_args.append(f"--exclude={folder}")
    return exclude_args


def apply_replacements_to_patch(patch_stream, replacements):
    patch_content = patch_stream.getvalue().decode("utf-8")
    for replacement in replacements:
        patch_content = patch_content.replace(replacement["from"], replacement["to"])
    return io.BytesIO(patch_content.encode("utf-8"))
