import uuid
from couchdbkit.exceptions import BulkSaveError
from django.test import TestCase, SimpleTestCase
import os
from django.test.utils import override_settings
from casexml.apps.case.mock import CaseBlock, CaseFactory, CaseStructure, CaseIndex
from casexml.apps.case.models import CommCareCase
from casexml.apps.case.templatetags.case_tags import get_case_hierarchy
from casexml.apps.case.tests.util import delete_all_cases
from casexml.apps.case.xml import V2, V1
from casexml.apps.case.exceptions import IllegalCaseId
from corehq.form_processor.interfaces.case import CaseInterface
from corehq.util.test_utils import TestFileMixin
from corehq.form_processor.interfaces.processor import FormProcessorInterface
from corehq.form_processor.generic import GenericCommCareCase, GenericCommCareCaseIndex


class SimpleCaseBugTests(SimpleTestCase):

    def test_generate_xml_with_no_date_modified(self):
        # before this test was added both of these calls failed
        for version in (V1, V2):
            CommCareCase(_id='test').to_xml(version)


@override_settings(CASEXML_FORCE_DOMAIN_CHECK=False)
class CaseBugTest(TestCase, TestFileMixin):
    """
    Tests bugs that come up in case processing
    """
    file_path = ('data', 'bugs')
    root = os.path.dirname(__file__)

    def setUp(self):
        delete_all_cases()

    def test_conflicting_ids(self):
        """
        If a form and a case share an ID it's a conflict
        """
        xml_data = self.get_xml('id_conflicts')
        with self.assertRaises(BulkSaveError):
            FormProcessorInterface.submit_form_locally(xml_data)

    def test_empty_case_id(self):
        """
        Ensure that form processor fails on empty id
        """
        xml_data = self.get_xml('empty_id')
        response, form, cases = FormProcessorInterface.submit_form_locally(xml_data)
        self.assertIn('IllegalCaseId', response.content)

    def _testCornerCaseDatatypeBugs(self, value):

        def _test(custom_format_args):
            case_id = uuid.uuid4().hex
            format_args = {
                'case_id': case_id,
                'form_id': uuid.uuid4().hex,
                'user_id': uuid.uuid4().hex,
                'case_name': 'data corner cases',
                'case_type': 'datatype-check',
            }
            format_args.update(custom_format_args)
            for filename in ['bugs_in_case_create_datatypes', 'bugs_in_case_update_datatypes']:
                xml_data = self.get_xml(filename).format(**format_args)
                response, form, [case] = FormProcessorInterface.submit_form_locally(xml_data)

                self.assertEqual(format_args['user_id'], case.user_id)
                self.assertEqual(format_args['case_name'], case.name)
                self.assertEqual(format_args['case_type'], case.type)

        _test({'case_name': value})
        _test({'case_type': value})
        _test({'user_id': value})

    def testDateInCasePropertyBug(self):
        """
        Submits a case name/case type/user_id that looks like a date
        """
        self._testCornerCaseDatatypeBugs('2011-11-16')

    def testIntegerInCasePropertyBug(self):
        """
        Submits a case name/case type/user_id that looks like a number
        """
        self._testCornerCaseDatatypeBugs('42')

    def testDecimalInCasePropertyBug(self):
        """
        Submits a case name/case type/user_id that looks like a decimal
        """
        self._testCornerCaseDatatypeBugs('4.06')

    def testDuplicateCasePropertiesBug(self):
        """
        Submit multiple values for the same property in an update block
        """
        xml_data = self.get_xml('duplicate_case_properties')
        response, form, [case] = FormProcessorInterface.submit_form_locally(xml_data)
        self.assertEqual("", case.foo)

        xml_data = self.get_xml('duplicate_case_properties_2')
        response, form, [case] = FormProcessorInterface.submit_form_locally(xml_data)
        self.assertEqual("2", case.bar)

    def testMultipleCaseBlocks(self):
        """
        How do we do when submitting a form with multiple blocks for the same case?
        """
        xml_data = self.get_xml('multiple_case_blocks')
        response, form, [case] = FormProcessorInterface.submit_form_locally(xml_data)

        self.assertEqual('1630005', case.community_code)
        self.assertEqual('SantaMariaCahabon', case.district_name)
        self.assertEqual('TAMERLO', case.community_name)

        ids = case.xform_ids
        self.assertEqual(1, len(ids))
        self.assertEqual(form.id, ids[0])

    def testLotsOfSubcases(self):
        """
        How do we do when submitting a form with multiple blocks for the same case?
        """
        xml_data = self.get_xml('lots_of_subcases')
        response, form, cases = FormProcessorInterface.submit_form_locally(xml_data)
        self.assertEqual(11, len(cases))

    def testSubmitToDeletedCase(self):
        # submitting to a deleted case should succeed and affect the case
        case_id = 'immagetdeleted'
        deleted_doc_type = 'CommCareCase-Deleted'
        [xform, [case]] = FormProcessorInterface.post_case_blocks([
            CaseBlock(create=True, case_id=case_id, user_id='whatever',
                      update={'foo': 'bar'}).as_xml()
        ])
        self.assertEqual('bar', case.foo)
        case = CaseInterface.update_properties(case, doc_type=deleted_doc_type)

        self.assertEqual(deleted_doc_type, case.doc_type)
        [xform, [case]] = FormProcessorInterface.post_case_blocks([
            CaseBlock(create=False, case_id=case_id, user_id='whatever',
                      update={'foo': 'not_bar'}).as_xml()
        ])
        self.assertEqual('not_bar', case.foo)
        self.assertEqual(deleted_doc_type, case.doc_type)


class TestCaseHierarchy(TestCase):

    def setUp(self):
        delete_all_cases()

    def test_normal_index(self):
        cp = CaseInterface.create_from_generic(GenericCommCareCase(
            id='parent',
            name='parent',
            type='parent',
        ))

        CaseInterface.create_from_generic(GenericCommCareCase(
            id='child',
            name='child',
            type='child',
            indices=[GenericCommCareCaseIndex(
                identifier='parent',
                referenced_type='parent',
                referenced_id='parent'
            )],
        ))

        hierarchy = get_case_hierarchy(cp, {})
        self.assertEqual(2, len(hierarchy['case_list']))
        self.assertEqual(1, len(hierarchy['child_cases']))

    def test_recursive_indexes(self):
        c = CaseInterface.create_from_generic(GenericCommCareCase(
            id='infinite-recursion',
            name='infinite_recursion',
            type='bug',
            indices=[GenericCommCareCaseIndex(
                identifier='self',
                referenced_type='bug',
                referenced_id='infinite-recursion'
            )],
        ))
        # this call used to fail with infinite recursion
        hierarchy = get_case_hierarchy(c, {})
        self.assertEqual(1, len(hierarchy['case_list']))

    def test_complex_index(self):
        factory = CaseFactory()
        cp = factory.create_or_update_case(CaseStructure(case_id='parent', attrs={'case_type': 'parent'}))[0]

        # cases processed according to ID order so ensure that this case is
        # processed after the task case by making its ID sort after task ID
        factory.create_or_update_case(CaseStructure(
            case_id='z_goal',
            attrs={'case_type': 'goal'},
            indices=[CaseIndex(CaseStructure(case_id='parent'), related_type='parent')],
            walk_related=False
        ))

        factory.create_or_update_case(CaseStructure(
            case_id='task1',
            attrs={'case_type': 'task'},
            indices=[
                CaseIndex(CaseStructure(case_id='z_goal'), related_type='goal', identifier='goal'),
                CaseIndex(CaseStructure(case_id='parent'), related_type='parent')
            ],
            walk_related=False,
        ))

        # with 'ignore_relationship_types' if a case got processed along the ignored relationship first
        # then it got marked as 'seen' and would be not be processed again when it came to the correct relationship
        type_info = {
            'task': {
                'ignore_relationship_types': ['parent']
            },
        }

        hierarchy = get_case_hierarchy(cp, type_info)
        self.assertEqual(3, len(hierarchy['case_list']))
        self.assertEqual(1, len(hierarchy['child_cases']))
        self.assertEqual(2, len(hierarchy['child_cases'][0]['case_list']))
        self.assertEqual(1, len(hierarchy['child_cases'][0]['child_cases']))
