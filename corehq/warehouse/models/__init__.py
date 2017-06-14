from corehq.warehouse.models.dimensions import (
    UserDim,
    GroupDim,
    LocationDim,
    DomainDim,
    UserLocationDim,
    UserGroupDim,
)

from corehq.warehouse.models.meta import (
    TableState,
)

from corehq.warehouse.models.facts import (
    ApplicationStatusFact,
    FormFact,
)

from corehq.warehouse.models.staging import (
    GroupStagingTable,
    DomainStagingTable,
    UserStagingTable,
    FormStagingTable,
    SyncLogStagingTable,
)


def get_cls_by_slug(slug):
    return {
        GroupStagingTable.slug: GroupStagingTable,
        DomainStagingTable.slug: DomainStagingTable,
        UserStagingTable.slug: UserStagingTable,
        FormStagingTable.slug: FormStagingTable,
        SyncLogStagingTable.slug: SyncLogStagingTable,

        UserDim.slug: UserDim,
        GroupDim.slug: GroupDim,
        LocationDim.slug: LocationDim,
        DomainDim.slug: DomainDim,
        UserLocationDim.slug: UserLocationDim,
        UserGroupDim.slug: UserGroupDim,

        ApplicationStatusFact.slug: ApplicationStatusFact,
        FormFact.slug: FormFact,
    }[slug]
