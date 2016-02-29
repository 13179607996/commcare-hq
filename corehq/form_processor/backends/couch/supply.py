import logging

from dimagi.utils.couch.database import iter_docs

from corehq.apps.commtrack.helpers import make_supply_point
from corehq.apps.commtrack.models import SupplyPointCase
from corehq.form_processor.abstract_models import AbstractSupplyInterface


class SupplyPointCouch(AbstractSupplyInterface):

    @classmethod
    def get_or_create_by_location(cls, location):
        sp = location.linked_supply_point()
        if not sp:
            sp = make_supply_point(location.domain, location)

            # todo: if you come across this after july 2015 go search couchlog
            # and see how frequently this is happening.
            # if it's not happening at all we should remove it.
            logging.warning('supply_point_dynamically_created, {}, {}, {}'.format(
                location.name,
                sp.case_id,
                location.domain,
            ))

        return sp

    @classmethod
    def get_by_location(cls, location):
        return location.linked_supply_point()

    @staticmethod
    def get_supply_point(supply_point_id):
        return SupplyPointCase.get(supply_point_id)

    @staticmethod
    def get_supply_points(supply_point_ids):
        supply_points = []
        for doc in iter_docs(SupplyPointCase.get_db(), supply_point_ids):
            supply_points.append(SupplyPointCase.wrap(doc))
        return supply_points
