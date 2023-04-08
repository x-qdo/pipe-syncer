import os
import re

from git import DiffIndex, Repo, Diff


class CustomApply:
    def __init__(self, target_repo: Repo, diff_index: DiffIndex, dry_run=False):
        self.diff_index = diff_index
        self.dry_run = dry_run
        self.target_repo = target_repo

    def apply(self):
        patch_applied = False
        for diff in self.diff_index:
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
        file_path = os.path.join(self.target_repo.working_dir, diff.b_path)
        diff_chunks = self._extract_diff_chunks(diff)

        with open(file_path, 'r') as f:
            file_lines = [line.strip('\n') for line in f.readlines()]

        for chunk in diff_chunks:
            context_start, context_end, removed_lines, added_lines = chunk

            start_position = self._search_context(file_lines, context_start, context_end, removed_lines)
            if start_position != -1:
                if not self.dry_run:
                    file_lines[start_position: start_position + len(removed_lines)] = added_lines
                print(f"Applied change in {diff.b_path} at line {start_position + 1}")
            else:
                print(f"Unable to apply change in {diff.b_path}:")
                print(str(diff))
                return False

        if not self.dry_run:
            with open(file_path, 'w') as f:
                f.writelines([f"{line}\n" for line in file_lines])
        return True

    def _extract_diff_chunks(self, diff: Diff):
        diff_chunks = []
        diff_string = diff.diff.decode()
        hunks = re.findall(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', diff_string)
        hunk_contents = re.split(r'@@ -\d+,\d+ \+\d+,\d+ @@(?:\n)?', diff_string)[1:]

        for hunk, content in zip(hunks, hunk_contents):
            a_start, a_lines, b_start, b_lines = map(int, hunk)
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
                        diff_chunks.append((before_context, after_context, removed_lines, added_lines))
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

            diff_chunks.append((before_context, after_context, removed_lines, added_lines))

        return diff_chunks

    def _search_context(self, file_lines, context_start, context_end, removed_lines):
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

        max_context_match_start_len = len(context_start)
        max_context_match_end_len = len(context_end)

        # Remove whitespaces from context lines
        # context_start = [line.replace(" ", "") for line in context_start]
        # context_end = [line.replace(" ", "") for line in context_end]

        #
        for context_match_start_len, context_match_end_len in generate_combinations(max_context_match_start_len,
                                                                                    max_context_match_end_len):
            # taking [l-N:l] lines from the context start
            possible_context_start = context_start[
                                     len(context_start) - context_match_start_len:len(context_start)]

            # taking [0:N] lines from the context end
            possible_context_end = context_end[0:context_match_end_len]

            for idx in range(len(file_lines) - context_match_start_len
                             - context_match_end_len - len(removed_lines) + 1):
                file_context_start = file_lines[idx:idx + context_match_start_len]

                file_context_end_start_index = idx + context_match_start_len + len(removed_lines)
                file_context_end_end_index = idx + context_match_start_len + len(
                    removed_lines) + context_match_end_len
                file_context_end = file_lines[file_context_end_start_index:file_context_end_end_index]

                # Remove whitespaces from file context lines
                # file_context_start = [line.replace(" ", "") for line in file_context_start]
                # file_context_end = [line.replace(" ", "") for line in file_context_end]

                if file_context_start == possible_context_start and \
                        file_context_end == possible_context_end:
                    return idx + context_match_start_len

        return -1
