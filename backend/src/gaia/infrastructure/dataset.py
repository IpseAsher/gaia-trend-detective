from gaia.application.health import DatasetHealth, DatasetUnavailable


class UnconfiguredDatasetRepository:
    """Fail closed until the official SQLite and manifest are provisioned.

    Dataset selection and the verified SQLite adapter belong to the data phase.
    This initial adapter never creates a database or reports synthetic health.
    """

    def verify(self) -> DatasetHealth:
        raise DatasetUnavailable
