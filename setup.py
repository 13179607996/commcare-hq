#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='casexml',
    version='1.0.0',
    description='Dimagi CaseXML for Django',
    author='Dimagi',
    author_email='dev@dimagi.com',
    url='http://www.dimagi.com/',
    install_requires=[
        'celery==3.0.15',
        'jsonobject-couchdbkit>=0.6.5.2',
        'couchforms==3.0.2',
        'couchexport',
        'decorator',
        'dimagi-utils>=1.0.9',
        'django==1.5.5',
        'requests==2.0.0',
        'django-digest',
        'lxml',
        'mock',  # Actually a missing dimagi-utils dep?
        'requests==2.0.0',
        'restkit',
        'python-digest',
        'pytz',
        'simplejson',
        'Pillow==2.0.0',
        'unittest2',  # Actually a missing dimagi-utils dep?
        'django-redis==3.3',
        'redis==2.8.0',
    ],
    tests_require=[
        'coverage',
        'django-coverage',
    ],
    packages=find_packages(exclude=['*.pyc']),
    include_package_data=True,
)
