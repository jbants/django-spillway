#!/usr/bin/env python
import os
import sys
import shutil
import tempfile

from django.conf import settings
import django

TMPDIR = tempfile.mkdtemp(prefix='spillway_')

DEFAULT_SETTINGS = {
    'INSTALLED_APPS': (
        'django.contrib.gis',
        'spillway',
        'tests',
    ),
    'DATABASES': {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.spatialite',
            'NAME': ':memory:'
        }
    },
    'MEDIA_ROOT': TMPDIR
}

def teardown():
    try:
        shutil.rmtree(TMPDIR)
    except OSError:
        print('Failed to remove {}'.format(TMPDIR))

def runtests():
    if not settings.configured:
        settings.configure(**DEFAULT_SETTINGS)
    # Compatibility with Django 1.7's stricter initialization
    if hasattr(django, 'setup'):
        django.setup()
    parent = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, parent)
    try:
        from django.test.runner import DiscoverRunner
        runner_class = DiscoverRunner
    except ImportError:
        from django.test.simple import DjangoTestSuiteRunner
        runner_class = DjangoTestSuiteRunner
    failures = runner_class(
        verbosity=1, interactive=True, failfast=False).run_tests(['tests'])
    teardown()
    sys.exit(failures)

if __name__ == '__main__':
    runtests()
