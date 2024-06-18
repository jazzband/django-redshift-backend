from django_redshift_backend.meta import DistKey, SortKey  # noqa

# py38 or later
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("package-name")
except PackageNotFoundError:
    # package is not installed
    pass
