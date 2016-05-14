from setuptools import setup, find_packages

requires = [
    'django',
    'psycopg2',
]


def read(filename):
    with open(filename) as f:
        return f.read()


setup(
    name='django-redshift-backend',
    version='0.4',
    packages=find_packages(),
    url='https://github.com/shimizukawa/django-redshift-backend',
    license='Apache Software License',
    author='shimizukawa',
    author_email='shimizukawa@gmail.com',
    description='Redshift database backend for Django',
    long_description=read('README.rst'),
    install_requires=requires,
)

