import os
import re
import textwrap

import pyperclip
from git import DiffIndex, Repo, Diff


class DiffHunk:
    def __init__(self, a_start, a_lines, b_start, b_lines):
        self.a_start = a_start
        self.a_lines = a_lines
        self.b_start = b_start
        self.b_lines = b_lines
        self.before_context = ""
        self.after_context = ""
        self.removed_lines = ""
        self.added_lines = ""

    def set_content(self, before_context, after_context, removed_lines, added_lines):
        self.before_context = before_context
        self.after_context = after_context
        self.removed_lines = removed_lines
        self.added_lines = added_lines


class CustomApply:
    def __init__(self, target_repo: Repo, dry_run=False, interactive=False):
        self.dry_run = dry_run
        self.interactive = interactive
        self.target_repo = target_repo

    def apply(self, diff_index: DiffIndex):
        patch_applied = False
        for diff in diff_index:
            if diff.deleted_file:
                patch_applied = self._handle_delete(diff)
            elif diff.new_file:
                patch_applied = self._handle_create(diff)
            elif diff.renamed_file:
                patch_applied = self._handle_rename(diff)
            else:
                patch_applied = self._handle_modify(diff)

        return patch_applied

    def _handle_delete(self, diff: Diff):
        file_path = os.path.join(self.target_repo.working_dir, diff.a_path)
        if os.path.exists(file_path):
            if not self.dry_run:
                os.remove(file_path)
                print(f"Deleted file {diff.a_path}")
            return True
        return False

    def _handle_create(self, diff: Diff):
        file_path = os.path.join(self.target_repo.working_dir, diff.b_path)
        dir_path = os.path.dirname(file_path)  # get the directory path

        # make sure all directories exist
        os.makedirs(dir_path, exist_ok=True)
        if not os.path.exists(file_path):
            if not self.dry_run:
                with open(file_path, 'w') as f:
                    f.write(diff.b_blob.data_stream.read().decode('utf-8'))
                print(f"Created file {diff.b_path}")
            return True
        return False

    def _handle_rename(self, diff: Diff):
        old_file_path = os.path.join(self.target_repo.working_dir, diff.a_path)
        new_file_path = os.path.join(self.target_repo.working_dir, diff.b_path)

        if os.path.exists(old_file_path):
            if not self.dry_run:
                os.rename(old_file_path, new_file_path)
                print(f"Renamed file {diff.a_path} to {diff.b_path}")
            return True
        return False

    def _handle_modify(self, diff: Diff):
        print(f"Working on M path in file {diff.b_path}")
        file_path = os.path.join(self.target_repo.working_dir, diff.b_path)
        if not os.path.exists(file_path):
            print(f"Target file path not found, maybe file was already renamed or removed: {diff.b_path}")
            return False

        diff_chunks = self._extract_diff_chunks(diff)

        with open(file_path, 'r') as f:
            file_lines = [line.strip('\n') for line in f.readlines()]

        all_patches_applied = True
        for chunk in diff_chunks:
            start_position, replace_len = self._search_context(file_lines, chunk)
            if start_position != -1:
                if not self.dry_run:
                    file_lines[start_position: start_position + replace_len] = chunk.added_lines
                print(f"Applied change in {diff.b_path} at line {start_position + 1}")
            else:
                all_patches_applied = False

        if not all_patches_applied:
            patch = f"--- a/{diff.a_path}\n" \
                    + f"+++ a/{diff.b_path}\n" \
                    + diff.diff.decode() \
                    + "\n--\n"

            if self.interactive:
                print(f"Unable to apply patch, moved to you clipboard")
                pyperclip.copy(patch)
                input("To continue press any key...")
            else:
                print(f"Unable to apply patch, you can copy it and use IDE:")
                print(f"\n{patch}")
            return False

        if not self.dry_run:
            with open(file_path, 'w') as f:
                f.writelines([f"{line}\n" for line in file_lines])
        return True

    def _extract_diff_chunks(self, diff: Diff) -> list[DiffHunk]:
        diff_chunks = []
        diff_string = diff.diff.decode()

        hunks = re.findall(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', diff_string)
        hunk_contents = re.split(r'@@ -\d+,\d+ \+\d+,\d+ @@(?:\n)?', diff_string)[1:]

        for hunk, content in zip(hunks, hunk_contents):
            a_start, a_lines, b_start, b_lines = map(int, hunk)
            diff_hunk = DiffHunk(a_start, a_lines, b_start, b_lines)

            content_lines = content.splitlines()

            before_context = []
            after_context = []
            removed_lines = []
            added_lines = []

            after_modifications = False
            last_line_was_context = False
            for line in content_lines:
                if line.startswith('\\'):  # Ignore lines starting with '\'
                    continue

                if line.startswith('+') or line.startswith('-'):
                    if last_line_was_context and (removed_lines or added_lines):
                        # If the last line was a context line and we already have removed or added lines,
                        # we should start a new hunk for the broken context
                        diff_hunk.set_content(before_context, after_context, removed_lines, added_lines)
                        diff_chunks.append(diff_hunk)
                        diff_hunk = DiffHunk(a_start, a_lines, b_start, b_lines)

                        before_context = after_context
                        after_context = []
                        removed_lines = []
                        added_lines = []

                    if line.startswith('+'):
                        added_lines.append(line[1:])
                    elif line.startswith('-'):
                        removed_lines.append(line[1:])
                    after_modifications = True
                    last_line_was_context = False
                else:
                    line = line[1:]  # Remove the space in front of the context lines
                    if after_modifications:
                        after_context.append(line)
                    else:
                        before_context.append(line)
                    last_line_was_context = True

            diff_hunk.set_content(before_context, after_context, removed_lines, added_lines)
            diff_chunks.append(diff_hunk)

        return diff_chunks

    def _format_log_lines(self, lines, prefix="| "):
        if len(lines):
            return textwrap.indent("\n".join(lines), prefix) + "\n"
        return ""

    def _search_context(self, file_lines, hunk: DiffHunk):
        """
        Locating line number based on hunk surround context using variable lengths

        :param file_lines:
        :param context_start:
        :param context_end:
        :param removed_lines:
        :return:
        """

        def generate_combinations(start_len, end_len):
            combinations = [(i, j) for i in range(start_len + 1) for j in
                            range(end_len + 1)]
            combinations.sort(key=sum, reverse=True)

            # Allow zero contexts only if we don't have any context
            if start_len == 0 or end_len == 0:
                return list(filter(lambda x: x[0] != 0 or x[1] != 0, combinations))
            else:
                return list(filter(lambda x: x[0] != 0 and x[1] != 0, combinations))

        max_start_len = len(hunk.before_context)
        max_end_len = len(hunk.after_context)

        # Remove whitespaces from context lines
        # context_start = [line.replace(" ", "") for line in context_start]
        # context_end = [line.replace(" ", "") for line in context_end]

        #
        for match_start_len, match_end_len in generate_combinations(max_start_len, max_end_len):
            # taking [l-N:l] lines from the context start
            possible_context_start = hunk.before_context[
                                     len(hunk.before_context) - match_start_len:len(hunk.before_context)]

            # taking [0:N] lines from the context end
            possible_context_end = hunk.after_context[0:match_end_len]
            possible_match_found = False

            for idx in range(len(file_lines) - match_start_len - match_end_len - len(hunk.removed_lines) + 1):
                file_context_start = file_lines[idx:idx + match_start_len]

                # Remove whitespaces from file context lines
                # file_context_start = [line.replace(" ", "") for line in file_context_start]
                # file_context_end = [line.replace(" ", "") for line in file_context_end]

                if file_context_start == possible_context_start:
                    file_context_end_start_index = idx + match_start_len + len(hunk.removed_lines)
                    file_context_end_end_index = idx + match_start_len + len(hunk.removed_lines) + match_end_len
                    file_context_end = file_lines[file_context_end_start_index:file_context_end_end_index]

                    file_context_applied_start_index = idx + match_start_len + len(hunk.added_lines)
                    file_context_applied_end_index = idx + match_start_len + len(hunk.added_lines) + match_end_len
                    file_context_applied = file_lines[file_context_applied_start_index:file_context_applied_end_index]

                    if file_context_end == possible_context_end:
                        # Check if the deleted lines match the lines in the original file
                        file_removed_lines_start_idx = idx + match_start_len
                        file_removed_lines_end_idx = file_context_end_start_index
                        file_removed_lines = file_lines[file_removed_lines_start_idx:file_removed_lines_end_idx]

                        if file_removed_lines == hunk.removed_lines:
                            print(
                                f"Found match with context at {idx + match_start_len}: {match_start_len}/{match_end_len}")
                            print(self._format_log_lines(file_context_start)
                                  + self._format_log_lines(hunk.removed_lines, " -")
                                  + self._format_log_lines(hunk.added_lines, " +")
                                  + self._format_log_lines(file_context_end))

                            return idx + match_start_len, len(hunk.removed_lines)
                        else:
                            print(f"Fount potential match, "
                                  f"but content differ, at {idx + match_start_len}: {match_start_len}/{match_end_len}")
                            print("Expected:")
                            print(self._format_log_lines(hunk.removed_lines))
                            print("Found:")
                            print(self._format_log_lines(file_removed_lines))
                            possible_match_found = True

                    elif file_context_applied == possible_context_end:
                        file_added_lines_end_idx = idx + match_start_len + len(hunk.added_lines)
                        file_added_lines = file_lines[idx + match_start_len:file_added_lines_end_idx]

                        if file_added_lines == hunk.added_lines:
                            print(f"Diff already applied at {idx + match_start_len}: {match_start_len}/{match_end_len}")
                            print(self._format_log_lines(file_added_lines, " +"))
                            return idx + match_start_len, len(hunk.added_lines)

            if possible_match_found:
                # We found potential match in a file, and we do not need to reduce context to locate
                # the potential match
                return -1, -1

        print("Couldn't find context for")
        print(self._format_log_lines(hunk.before_context)
              + self._format_log_lines(hunk.removed_lines, " -")
              + self._format_log_lines(hunk.added_lines, " +")
              + self._format_log_lines(hunk.after_context))
        return -1, -1
