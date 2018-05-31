ToDo for releasing
=====================

1. check travis-ci testing result
2. check release version in setup.py and README.rst
3. build distribtion files: ``python setup.py release sdist bdist_wheel``
3. make a release: ``twine upload dist/<new-version-files>``
4. check PyPI page
5. tagging with version name. e.g.: git tag 0.4
6. bump version in setup.py and README.rst

