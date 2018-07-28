.. release procedure

Prepare newest packages:

* setuptools
* wheel
* twine

Procedure:

1. check travis-ci testing result: https://travis-ci.org/shimizukawa/django-redshift-backend
2. check release version in ``setup.py`` and ``CHANGES.rst``
3. build distribtion files: ``python setup.py release sdist bdist_wheel``
4. make a test release: ``twine upload --repository-url https://test.pypi.org/legacy dist/<new-version-files>``
5. make a release: ``twine upload dist/<new-version-files>``
6. check PyPI page: https://pypi.org/p/django-redshift-backend
7. tagging with version name. e.g.: git tag 0.4
8. bump version in setup.py and README.rst and commit/push them onto GitHub

