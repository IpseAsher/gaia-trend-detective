from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DatasetHealth:
    dataset_version: str


class DatasetUnavailable(Exception):
    code = "dataset_unavailable"
    message = "The precipitation dataset is not available yet."


class DatasetIncompatible(DatasetUnavailable):
    code = "dataset_incompatible"
    message = "The precipitation dataset could not be verified."


class DatasetRepository(Protocol):
    def verify(self) -> DatasetHealth:
        """Verify read-only access, integrity, and dataset/schema versions.

        Raise DatasetUnavailable or DatasetIncompatible if verification fails.
        """
        ...


@dataclass(frozen=True)
class CheckHealth:
    repository: DatasetRepository

    def execute(self) -> DatasetHealth:
        return self.repository.verify()
