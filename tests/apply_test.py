import os
import shutil
import tempfile
import unittest

import pytest
from git import Repo
from parameterized import parameterized

from apply import CustomApply


def init_test_repos():
    # Create temporary directories for source and target repos
    source_path = tempfile.mkdtemp()
    target_path = tempfile.mkdtemp()

    # Initialize the source and target repositories
    source_repo = Repo.init(source_path)
    target_repo = Repo.init(target_path)

    return source_repo, target_repo


def create_and_commit_file(repo, file_path, content, commit_message):
    with open(os.path.join(repo.working_tree_dir, file_path), 'w') as f:
        f.write(content)
    repo.index.add([file_path])
    repo.index.commit(commit_message)


class TestCustomApply(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def capfd(self, capfd):
        self.capfd = capfd

    def setUp(self):
        # Initialize the test repositories
        self.source_repo, self.target_repo = init_test_repos()

        # Create an initial file in both repositories
        self.initial_content = "\n".join([f"Line {idx}" for idx in range(1, 100)])
        create_and_commit_file(self.source_repo, 'file.txt', self.initial_content, "Initial commit")
        create_and_commit_file(self.target_repo, 'file.txt', self.initial_content, "Initial commit")

    def test_handle_create(self):
        # Create a new file in the source repo and commit it
        new_file_content = "This is a new file\n"
        create_and_commit_file(self.source_repo, 'new_file.txt', new_file_content, "Add new file")

        # Get the commit object and generate the diff
        commit = self.source_repo.commit('HEAD')
        diff = commit.parents[0].diff(commit, create_patch=True, ignore_cr_at_eol=True)

        # Apply the diff using the CustomApply class
        custom_apply = CustomApply(self.target_repo, diff)
        custom_apply.apply()

        # Assert that the new file exists in the target repo and has the same content
        new_file_target_path = os.path.join(self.target_repo.working_tree_dir, 'new_file.txt')
        self.assertTrue(os.path.exists(new_file_target_path), "New file should exist in the target repo")
        with open(new_file_target_path, 'r') as f:
            target_content = f.read()
        self.assertEqual(new_file_content, target_content, "New file content should match")

    @parameterized.expand([
        (
                'multiple hunks',
                'Applied change in file.txt at line 22\nApplied change in file.txt at line 92',

                "".join([f"Line {idx}\n" for idx in range(1, 20)])
                + 'Line 20\nLine 21\nModified Line 23\n'
                + "".join([f"Line {idx}\n" for idx in range(23, 90)])
                + 'Line 90\nLine 91\nModified Line 93\n',

                "".join([f"Line {idx}\n" for idx in range(1, 100)]),

                "".join([f"Line {idx}\n" for idx in range(1, 20)])
                + 'Line 20\nLine 21\nModified Line 23\n'
                + "".join([f"Line {idx}\n" for idx in range(23, 90)])
                + 'Line 90\nLine 91\nModified Line 93\n',
        ),
        (
                'diff in both ends of the file',
                'Applied change in file.txt at line 3\nApplied change in file.txt at line 9',

                'Line 1\nLine 2\nModified Line 3\n'
                + "".join([f"Line {idx}\n" for idx in range(4, 9)])
                + 'Modified Line 9\n\n',

                "".join([f"Line {idx}\n" for idx in range(1, 100)]),

                'Line 1\nLine 2\nModified Line 3\n'
                + "".join([f"Line {idx}\n" for idx in range(4, 9)])
                + 'Modified Line 9\n\n',
        ),
        (
                'partial match additional content',
                'Applied change in file.txt at line 3',

                'Line 1\nLine 2\nModified Line 3\n'
                + "".join([f"Line {idx}\n" for idx in range(4, 10)]),

                'Line 1\nLine 2\nLine 3\nLine 4\nModified Line 5\n'
                + "".join([f"Line {idx}\n" for idx in range(6, 100)]),

                'Line 1\nLine 2\nModified Line 3\nLine 4\nModified Line 5\n'
                + "".join([f"Line {idx}\n" for idx in range(6, 10)]),
        ),
        (
                'partial front match single line',
                'Applied change in file.txt at line 2',
                'Line 1\nModified Line 2\n'
                + "".join([f"Line {idx}\n" for idx in range(3, 10)]),

                "".join([f"Line {idx}\n" for idx in range(1, 100)]),

                'Line 1\nModified Line 2\n'
                + "".join([f"Line {idx}\n" for idx in range(3, 10)]),
        ),
        (
                'full match single line',
                'Applied change in file.txt at line 3',

                'Line 1\nLine 2\nModified Line 3\n'
                + "".join([f"Line {idx}\n" for idx in range(4, 10)]),

                "".join([f"Line {idx}\n" for idx in range(1, 100)]),

                'Line 1\nLine 2\nModified Line 3\n'
                + "".join([f"Line {idx}\n" for idx in range(4, 10)]),
        ),
    ])
    def test_handle_modify(self, name, expected_output, source_content, target_content, expected_target_content):
        create_and_commit_file(self.source_repo, 'file.txt', source_content, "Modify file")
        create_and_commit_file(self.target_repo, 'file.txt', target_content, "Add extra line")

        # Get the commit object and generate the diff
        commit = self.source_repo.commit('HEAD')
        diff = commit.parents[0].diff(commit, create_patch=True, ignore_cr_at_eol=True)

        # Apply the diff using the CustomApply class
        custom_apply = CustomApply(self.target_repo, diff)
        custom_apply.apply()
        output, err = self.capfd.readouterr()  # https://github.com/pytest-dev/pytest/issues/2504#issuecomment-309475790
        self.assertIn(expected_output, output, f"{name}: {output}")

        # Assert that the modified file in the target repo has the expected content
        modified_file_target_path = os.path.join(self.target_repo.working_tree_dir, 'file.txt')
        with open(modified_file_target_path, 'r') as f:
            target_content = f.read()
        self.assertEqual(expected_target_content, target_content,
                         f"{name}: Modified file content should match")

    # def test_handle_delete(self):
    #     # Delete an existing file in the source repo and commit it
    #     # ...
    #
    #     # Generate the diff between the commits
    #     # ...
    #
    #     # Apply the diff using the CustomApply class
    #     custom_apply = CustomApply(self.target_repo, diff)
    #     custom_apply.apply()
    #
    #     # Assert that the deleted file does not exist in the target repo
    #     # ...

    def tearDown(self):
        # Remove the temporary directories created in setUp
        shutil.rmtree(self.source_repo.working_tree_dir)
        shutil.rmtree(self.target_repo.working_tree_dir)
