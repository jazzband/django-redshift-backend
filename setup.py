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
    version='0.8',
    packages=find_packages(),
    url='http://django-redshift-backend.rtfd.io/',
    license='Apache Software License',
    author='shimizukawa',
    author_email='shimizukawa@gmail.com',
    description='Redshift database backend for Django',
    long_description=read('README.rst'),
    install_requires=requires,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Framework :: Django',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.9',
        'Framework :: Django :: 1.10',
        'Framework :: Django :: 1.11',
        'Intended Audience :: Developers',
        'Environment :: Plugins',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
