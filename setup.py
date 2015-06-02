from setuptools import setup, find_packages

requires = [
    'django',
    'psycopg2',
]

setup(
    name='django-redshift-backend',
    version='0.1.2',
    packages=find_packages(),
    url='https://github.com/shimizukawa/django-redshift-backend',
    license='Apache Software License',
    author='shimizukawa',
    author_email='shimizukawa@gmail.com',
    description='Redshift database backend for Django',
    long_description='Redshift database backend for Django is tested with django-1.7.6 and python-2.7.x',
    install_requires=requires,
)

