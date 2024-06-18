from .meta import DistKey, SortKey  # noqa

# py38 or later
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("django-redshift-backend")
except PackageNotFoundError:
    # package is not installed
    pass
