import os
from collections import defaultdict

import semver
from git import DiffIndex
from git.exc import GitCommandError


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


def apply_replacements_to_bytes(string_buffer, replacements, direction):
    if string_buffer is None:
        return string_buffer

    string = string_buffer.decode()

    for replacement in replacements:
        # determine a direction of replace for a source we replace to -> from
        #      for target from -> to
        if direction == 'source':
            replace_from = replacement["to"]
            replace_to = replacement["from"]
        else:
            replace_from = replacement["from"]
            replace_to = replacement["to"]

        string = string.replace(replace_from, replace_to)

    return string.encode()


def apply_replacements_to_patch(diff_index: DiffIndex, replacements, direction='source'):
    if len(replacements) == 0:
        return diff_index

    for diff in diff_index:
        diff.a_rawpath = apply_replacements_to_bytes(diff.a_rawpath, replacements, direction)
        diff.b_rawpath = apply_replacements_to_bytes(diff.b_rawpath, replacements, direction)
        diff.diff = apply_replacements_to_bytes(diff.diff, replacements, direction)

    return diff_index


def commit_changes(repo, message):
    try:
        repo.git.commit("-m", message)
    except GitCommandError as e:
        # Parse the error message
        error_message = str(e)
        if 'nothing to commit, working tree clean' in error_message:
            print('No changes to commit, skipping...')
        else:
            print(f'An error occurred when committing changes: {error_message}')
            raise e  # re-raise the exception for any other errors
    return True
