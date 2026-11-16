import shutil

import pytest

from gaia.infrastructure.dataset import DEFAULT_DATA_DIRECTORY


@pytest.fixture
def dataset_copy(tmp_path):
    if not (DEFAULT_DATA_DIRECTORY / "gaia.sqlite").is_file():
        pytest.skip("Generate the real-source dataset with scripts/prepare_data.py first")
    directory = tmp_path / "dataset # verified"
    directory.mkdir()
    database, manifest = directory / "gaia.sqlite", directory / "manifest.json"
    shutil.copyfile(DEFAULT_DATA_DIRECTORY / "gaia.sqlite", database)
    shutil.copyfile(DEFAULT_DATA_DIRECTORY / "manifest.json", manifest)
    return database, manifest
