from couchdbkit.ext.django.schema import Document, BooleanProperty, StringProperty
from casexml.apps.stock.models import DocDomainMapping
from datetime import datetime
from django.db import models
from corehq.apps.commtrack.models import SupplyPointCase


class ILSMigrationCheckpoint(models.Model):
    domain = models.CharField(max_length=100)
    date = models.DateTimeField(null=True)
    api = models.CharField(max_length=100)
    limit = models.PositiveIntegerField()
    offset = models.PositiveIntegerField()


class ILSGatewayConfig(Document):
    enabled = BooleanProperty(default=False)
    domain = StringProperty()
    url = StringProperty(default="http://ilsgateway.com/api/v0_1")
    username = StringProperty()
    password = StringProperty()

    @classmethod
    def for_domain(cls, name):
        try:
            mapping = DocDomainMapping.objects.get(domain_name=name, doc_type='ILSGatewayConfig')
            return cls.get(docid=mapping.doc_id)
        except DocDomainMapping.DoesNotExist:
            return None

    @classmethod
    def get_all_configs(cls):
        mappings = DocDomainMapping.objects.filter(doc_type='ILSGatewayConfig')
        configs = [cls.get(docid=mapping.doc_id) for mapping in mappings]
        return configs

    @classmethod
    def get_all_enabled_domains(cls):
        configs = cls.get_all_configs()
        return [c.domain for c in filter(lambda config: config.enabled, configs)]

    @property
    def is_configured(self):
        return True if self.enabled and self.url and self.password and self.username else False

    def save(self, **params):
        super(ILSGatewayConfig, self).save(**params)
        try:
            DocDomainMapping.objects.get(doc_id=self._id,
                                         domain_name=self.domain,
                                         doc_type="ILSGatewayConfig")
        except DocDomainMapping.DoesNotExist:
            DocDomainMapping.objects.create(doc_id=self._id,
                                            domain_name=self.domain,
                                            doc_type='ILSGatewayConfig')


class SupplyPointStatusValues(object):
    RECEIVED = "received"
    NOT_RECEIVED = "not_received"
    SUBMITTED = "submitted"
    NOT_SUBMITTED = "not_submitted"
    REMINDER_SENT = "reminder_sent"
    ALERT_SENT = "alert_sent"
    CHOICES = [RECEIVED, NOT_RECEIVED, SUBMITTED,
               NOT_SUBMITTED, REMINDER_SENT, ALERT_SENT]


class SupplyPointStatusTypes(object):
    DELIVERY_FACILITY = "del_fac"
    DELIVERY_DISTRICT = "del_dist"
    R_AND_R_FACILITY = "rr_fac"
    R_AND_R_DISTRICT = "rr_dist"
    SOH_FACILITY = "soh_fac"
    SUPERVISION_FACILITY = "super_fac"
    LOSS_ADJUSTMENT_FACILITY = "la_fac"
    DELINQUENT_DELIVERIES = "del_del"

    CHOICE_MAP = {
        DELIVERY_FACILITY: {SupplyPointStatusValues.REMINDER_SENT: "Waiting Delivery Confirmation",
                            SupplyPointStatusValues.RECEIVED: "Delivery received",
                            SupplyPointStatusValues.NOT_RECEIVED: "Delivery Not Received"},
        DELIVERY_DISTRICT: {SupplyPointStatusValues.REMINDER_SENT: "Waiting Delivery Confirmation",
                            SupplyPointStatusValues.RECEIVED: "Delivery received",
                            SupplyPointStatusValues.NOT_RECEIVED: "Delivery not received"},
        R_AND_R_FACILITY: {SupplyPointStatusValues.REMINDER_SENT: "Waiting R&R sent confirmation",
                           SupplyPointStatusValues.SUBMITTED: "R&R Submitted From Facility to District",
                           SupplyPointStatusValues.NOT_SUBMITTED: "R&R Not Submitted"},
        R_AND_R_DISTRICT: {SupplyPointStatusValues.REMINDER_SENT: "R&R Reminder Sent to District",
                           SupplyPointStatusValues.SUBMITTED: "R&R Submitted from District to MSD"},
        SOH_FACILITY: {SupplyPointStatusValues.REMINDER_SENT: "Stock on hand reminder sent to Facility",
                       SupplyPointStatusValues.SUBMITTED: "Stock on hand Submitted"},
        SUPERVISION_FACILITY: {SupplyPointStatusValues.REMINDER_SENT: "Supervision Reminder Sent",
                               SupplyPointStatusValues.RECEIVED: "Supervision Received",
                               SupplyPointStatusValues.NOT_RECEIVED: "Supervision Not Received"},
        LOSS_ADJUSTMENT_FACILITY: {SupplyPointStatusValues.REMINDER_SENT: "Lost/Adjusted Reminder sent to Facility"},
        DELINQUENT_DELIVERIES: {SupplyPointStatusValues.ALERT_SENT: "Delinquent deliveries summary sent to District"},
    }

    @classmethod
    def get_display_name(cls, type, value):
        return cls.CHOICE_MAP[type][value]

    @classmethod
    def is_legal_combination(cls, type, value):
        return type in cls.CHOICE_MAP and value in cls.CHOICE_MAP[type]


class SupplyPointStatus(models.Model):
    status_type = models.CharField(choices=((k, k) for k in SupplyPointStatusTypes.CHOICE_MAP.keys()),
                                   max_length=50)
    status_value = models.CharField(max_length=50,
                                    choices=((c, c) for c in SupplyPointStatusValues.CHOICES))
    status_date = models.DateTimeField(default=datetime.utcnow)
    supply_point = models.CharField(max_length=100, db_index=True)

    def save(self, *args, **kwargs):
        if not SupplyPointStatusTypes.is_legal_combination(self.status_type, self.status_value):
            raise ValueError("%s and %s is not a legal value combination" % \
                             (self.status_type, self.status_value))
        super(SupplyPointStatus, self).save(*args, **kwargs)

    def __unicode__(self):
        return "%s: %s" % (self.status_type, self.status_value)

    @property
    def name(self):
        return SupplyPointStatusTypes.get_display_name(self.status_type, self.status_value)

    @classmethod
    def wrap_from_json(cls, obj, domain):
        sp = SupplyPointCase.view('hqcase/by_domain_external_id',
                                  key=[domain, str(obj['supply_point'])],
                                  reduce=False,
                                  include_docs=True).first()
        obj['supply_point'] = sp._id
        del obj['id']
        return cls(**obj)

    class Meta:
        verbose_name = "Facility Status"
        verbose_name_plural = "Facility Statuses"
        get_latest_by = "status_date"
        ordering = ('-status_date',)


class DeliveryGroupReport(models.Model):
    supply_point = models.CharField(max_length=100, db_index=True)
    quantity = models.IntegerField()
    report_date = models.DateTimeField(default=datetime.now())
    message = models.CharField(max_length=100, db_index=True)
    delivery_group = models.CharField(max_length=1)

    class Meta:
        ordering = ('-report_date',)

    @classmethod
    def wrap_from_json(cls, obj, domain):
        sp = SupplyPointCase.view('hqcase/by_domain_external_id',
                                  key=[domain, str(obj['supply_point'])],
                                  reduce=False,
                                  include_docs=True).first()
        obj['supply_point'] = sp._id
        del obj['id']
        return cls(**obj)


class BaseReportingModel(models.Model):
    """
    A model to encapsulate aggregate (data warehouse) data used by a report.
    """
    supply_point = models.CharField(max_length=100, db_index=True)
    create_date = models.DateTimeField(editable=False)
    update_date = models.DateTimeField(editable=False)

    def save(self, *args, **kwargs):
        if not self.id:
            self.create_date = datetime.utcnow()
        self.update_date = datetime.utcnow()
        super(BaseReportingModel, self).save(*args, **kwargs)

    class Meta:
        abstract = True


class ReportingModel(BaseReportingModel):
    """
    A model to encapsulate aggregate (data warehouse) data used by a report.

    Just a BaseReportingModel + a date.
    """
    date = models.DateTimeField()                   # viewing time period

    class Meta:
        abstract = True


class SupplyPointWarehouseRecord(models.Model):
    """
    When something gets updated in the warehouse, create a record of having
    done that.
    """
    supply_point = models.CharField(max_length=100, db_index=True)
    create_date = models.DateTimeField()


class OrganizationSummary(ReportingModel):
    total_orgs = models.PositiveIntegerField(default=0) # 176
    average_lead_time_in_days = models.FloatField(default=0) # 28

    def __unicode__(self):
        return "%s: %s/%s" % (self.supply_point, self.date.month, self.date.year)


class GroupSummary(models.Model):
    """
    Warehouse data related to a particular category of reporting
    (e.g. stock on hand summary)
    """
    org_summary = models.ForeignKey('OrganizationSummary')
    title = models.CharField(max_length=50, blank=True, null=True) # SOH
    total = models.PositiveIntegerField(default=0)
    responded = models.PositiveIntegerField(default=0)
    on_time = models.PositiveIntegerField(default=0)
    complete = models.PositiveIntegerField(default=0) # "complete" = submitted or responded

    @property
    def late(self):
        return self.complete - self.on_time

    @property
    def not_responding(self):
        return self.total - self.responded

    @property
    def received(self):
        assert self.title in [SupplyPointStatusTypes.DELIVERY_FACILITY,
                              SupplyPointStatusTypes.SUPERVISION_FACILITY]
        return self.complete

    @property
    def not_received(self):
        assert self.title in [SupplyPointStatusTypes.DELIVERY_FACILITY,
                              SupplyPointStatusTypes.SUPERVISION_FACILITY]
        return self.responded - self.complete

    @property
    def sup_received(self):
        assert self.title in SupplyPointStatusTypes.SUPERVISION_FACILITY
        return self.complete

    @property
    def sup_not_received(self):
        assert self.title == SupplyPointStatusTypes.SUPERVISION_FACILITY
        return self.responded - self.complete

    @property
    def del_received(self):
        assert self.title == SupplyPointStatusTypes.DELIVERY_FACILITY
        return self.complete

    @property
    def del_not_received(self):
        assert self.title == SupplyPointStatusTypes.DELIVERY_FACILITY
        return self.responded - self.complete

    @property
    def not_submitted(self):
        assert self.title in [SupplyPointStatusTypes.SOH_FACILITY,
                              SupplyPointStatusTypes.R_AND_R_FACILITY]
        return self.responded - self.complete

    def __unicode__(self):
        return "%s - %s" % (self.org_summary, self.title)


class ProductAvailabilityData(ReportingModel):
    product = models.CharField(max_length=100, db_index=True)
    total = models.PositiveIntegerField(default=0)
    with_stock = models.PositiveIntegerField(default=0)
    without_stock = models.PositiveIntegerField(default=0)
    without_data = models.PositiveIntegerField(default=0)


class ProductAvailabilityDashboardChart(object):
    label_color = { "Stocked out" : "#a30808",
                    "Not Stocked out" : "#7aaa7a",
                    "No Stock Data" : "#efde7f"
                  }
    width = 900
    height = 300
    div = "product_availability_summary_plot_placeholder"
    legenddiv = "product_availability_summary_legend"
    xaxistitle = "Products"
    yaxistitle = "Facilities"


class Alert(ReportingModel):
    type = models.CharField(max_length=50, blank=True, null=True)
    number = models.PositiveIntegerField(default=0)
    text = models.TextField()
    url = models.CharField(max_length=100, blank=True, null=True)
    expires = models.DateTimeField()


