from gaia.application.health import CheckHealth, DatasetRepository
from gaia.infrastructure.dataset import UnconfiguredDatasetRepository
from gaia.presentation.api import create_api


def create_app(repository: DatasetRepository | None = None):
    """Composition root: wire infrastructure to application and HTTP adapters."""
    if repository is None:
        repository = UnconfiguredDatasetRepository()
    return create_api(CheckHealth(repository))


app = create_app()
