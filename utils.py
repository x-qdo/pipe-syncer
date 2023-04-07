import os
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
