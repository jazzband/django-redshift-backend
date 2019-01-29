.. release procedure

Procedure:

1. check travis-ci testing result: https://travis-ci.org/jazzband/django-redshift-backend
2. update release version/date in ``CHANGES.rst``
3. tagging with version name that MUST following semver. e.g.: ``git tag 1.0.1``
4. ``git push --tags`` to invoke release process on travis-ci.
5. approve release files. please check your email or https://jazzband.co/projects/django-redshift-backend
6. check PyPI page: https://pypi.org/p/django-redshift-backend
7. bump version in ``CHANGES.rst`` and commit/push them onto GitHub

