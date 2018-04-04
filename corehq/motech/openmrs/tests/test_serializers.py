# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

import datetime
import doctest

from django.test import SimpleTestCase

import corehq.motech.openmrs.serializers
from corehq.motech.openmrs.serializers import to_name, to_timestamp


class SerializerTests(SimpleTestCase):

    def test_to_timestamp_datetime(self):

        class CAT(datetime.tzinfo):
            def utcoffset(self, dt):
                return datetime.timedelta(hours=2)
            def tzname(self, dt):
                return "CAT"
            def dst(self, dt):
                return datetime.timedelta(0)

        dt = datetime.datetime(2017, 6, 27, 9, 36, 47, tzinfo=CAT())
        openmrs_timestamp = to_timestamp(dt)
        self.assertEqual(openmrs_timestamp, '2017-06-27T09:36:47.000+0200')

    def test_to_timestamp_datetime_str(self):
        datetime_str = '2017-06-27T09:36:47.396000Z'
        openmrs_timestamp = to_timestamp(datetime_str)
        self.assertEqual(openmrs_timestamp, '2017-06-27T09:36:47.396+0000')

    def test_to_name_numeric(self):
        commcare_name = 'Bush 2'
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, 'Bush -')

    def test_to_name_hyphen(self):
        commcare_name = 'Jean-Paul'
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, commcare_name)

    def test_to_name_spaces(self):
        commcare_name = 'van der Merwe'
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, commcare_name)

    def test_to_name_extendedlatin(self):
        commcare_name = 'Müller'
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, commcare_name)

    def test_to_name_ascii_apostrophe(self):
        commcare_name = "D'Urban"
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, commcare_name)

    def test_to_name_unicode_apostrophe(self):
        commcare_name = "DʼUrban"  # i.e. 'D\u02bcUrban'
        openmrs_name = to_name(commcare_name)
        self.assertEqual(openmrs_name, commcare_name)


class DocTests(SimpleTestCase):

    def test_doctests(self):
        results = doctest.testmod(corehq.motech.openmrs.serializers)
        self.assertEqual(results.failed, 0)
