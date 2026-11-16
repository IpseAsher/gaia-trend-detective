from gaia.application.health import CheckHealth, DatasetUnavailable
from gaia.application.analyses import AnalyzeRegions, GAIARepository
from gaia.infrastructure.dataset import DEFAULT_DATA_DIRECTORY, SQLiteDatasetRepository
from gaia.presentation.api import create_api


def create_app(repository: GAIARepository | None = None):
    """Composition root: wire infrastructure to application and HTTP adapters."""
    if repository is None:
        repository = SQLiteDatasetRepository(DEFAULT_DATA_DIRECTORY / "gaia.sqlite", DEFAULT_DATA_DIRECTORY / "manifest.json")
        # Verify at initialization while preserving the health endpoint's 503
        # contract when the prepared artifact is absent or incompatible.
        try:
            repository.verify()
        except DatasetUnavailable:
            pass
    return create_api(CheckHealth(repository), AnalyzeRegions(repository))


app = create_app()
