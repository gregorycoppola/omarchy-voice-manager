#!/usr/bin/env python3
"""Validate the referenced dataset. Definitions are loaded directly, never copied."""
from dataset_source import CATALOG, DATASET_ROOT, DATASET_REVISION
from command_catalog import EXPANSIONS

if __name__ == '__main__':
    print(f'Dataset: {DATASET_ROOT}')
    print(f'Revision: {DATASET_REVISION}; {len(CATALOG.intents)} intent schemas; '
          f'{len(EXPANSIONS)} compiled Skipper phrases')
    print('Edit the dataset repository, then restart Skipper to load the changes.')
