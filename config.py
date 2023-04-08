# Configuration
import logging
import yaml


def read_config(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


config = read_config('config.yaml')
log_level = config['log_level']
tag_prefix = config['tag_prefix']
sync_branch_prefix = config['sync_branch_prefix']