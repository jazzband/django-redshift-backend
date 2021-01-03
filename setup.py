from setuptools import setup, find_packages
import os

requires = [
    'django',
]


def read(filename):
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(fpath) as f:
        return f.read()


setup(
    name='django-redshift-backend',
    setup_requires=['setuptools_scm'],
    use_scm_version=True,
    packages=find_packages(),
    url='https://github.com/jazzband/django-redshift-backend',
    license='Apache Software License',
    author='shimizukawa',
    author_email='shimizukawa@gmail.com',
    description='Redshift database backend for Django',
    long_description=read('README.rst') + read('CHANGES.rst'),
    long_description_content_type='text/x-rst',
    install_requires=requires,
    extra_requires={
        'psycopg2-binary': ['psycopg2-binary'],
        'psycopg2': ['psycopg2'],
    },
    python_requires='>=3.6, <4',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'Framework :: Django :: 3.1',
        'Intended Audience :: Developers',
        'Environment :: Plugins',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
