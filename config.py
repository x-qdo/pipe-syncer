# Configuration
import logging

log_level = logging.DEBUG
# TODO migrate to config file like YAML
source_repo_path = "/Users/kkkk/projects/insly/pipeline-shared-library"
target_repo_path = "/Users/kkkk/projects/qdo/pipeline-shared-library"
tag_prefix = "v"
ignore_folders = ["test/DockerfileSSH", ".helm/", "Jenkinsfile", ".github/", "src/com/pipeline/data", ".git/",
                  ".sops.yaml"]
