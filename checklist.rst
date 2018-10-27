.. release procedure

Prepare newest packages:

* setuptools
* wheel
* twine

Procedure:

1. check travis-ci testing result: https://travis-ci.org/jazzband/django-redshift-backend
2. check release version in ``setup.py`` and ``CHANGES.rst``
3. tagging with version name that MUST following semver. e.g.: ``git tag 1.0.1``
4. build distribution files: ``python setup.py sdist bdist_wheel``
5. make a test release: ``twine upload --repository-url https://test.pypi.org/legacy dist/<new-version-files>``
6. make a release: ``twine upload dist/<new-version-files>``
7. check PyPI page: https://pypi.org/p/django-redshift-backend
8. bump version in ``CHANGES.rst`` and commit/push them onto GitHub

