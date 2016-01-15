from django.contrib.postgres.fields import JSONField
from django.db import models
from zentral.utils.mt_models import AbstractMTObject, MTObjectManager


class Source(AbstractMTObject):
    module = models.TextField()
    name = models.TextField()
    config = JSONField(blank=True, null=True)


class Link(AbstractMTObject):
    anchor_text = models.TextField()
    url = models.URLField()


class BusinessUnitManager(MTObjectManager):
    def current(self):
        return self.filter(machinesnapshot__mt_next__isnull=True).distinct().select_related('source').order_by('source__module', 'name')

class BusinessUnit(AbstractMTObject):
    source = models.ForeignKey(Source)
    reference = models.TextField()
    name = models.TextField()
    links = models.ManyToManyField(Link)

    objects = BusinessUnitManager()


class MachineGroupManager(MTObjectManager):
    def current(self):
        return self.filter(machinesnapshot__mt_next__isnull=True).distinct().select_related('source').order_by('source__module', 'name')

class MachineGroup(AbstractMTObject):
    source = models.ForeignKey(Source)
    reference = models.TextField()
    name = models.TextField()
    links = models.ManyToManyField(Link, related_name="+")
    machine_links = models.ManyToManyField(Link, related_name="+") # tmpl for links to machine in a group

    objects = MachineGroupManager()


class Machine(AbstractMTObject):
    serial_number = models.TextField(unique=True)


class OSVersion(AbstractMTObject):
    name = models.TextField(blank=True, null=True)
    major = models.PositiveIntegerField()
    minor = models.PositiveIntegerField()
    patch = models.PositiveIntegerField(blank=True, null=True)
    build = models.TextField(blank=True, null=True)


class SystemInfo(AbstractMTObject):
    computer_name = models.TextField(blank=True, null=True)
    hostname = models.TextField(blank=True, null=True)
    hardware_model = models.TextField(blank=True, null=True)
    hardware_serial = models.TextField(blank=True, null=True)
    cpu_type = models.TextField(blank=True, null=True)
    cpu_subtype = models.TextField(blank=True, null=True)
    cpu_brand = models.TextField(blank=True, null=True)
    cpu_physical_cores = models.PositiveIntegerField(blank=True, null=True)
    cpu_logical_cores = models.PositiveIntegerField(blank=True, null=True)
    physical_memory = models.BigIntegerField(blank=True, null=True)


class Certificate(AbstractMTObject):
    common_name = models.TextField()
    organization = models.TextField(blank=True, null=True)
    organizational_unit = models.TextField(blank=True, null=True)
    sha_1 = models.CharField(max_length=40)
    sha_256 = models.CharField(max_length=64, db_index=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    signed_by = models.ForeignKey('self', blank=True, null=True)


class OSXApp(AbstractMTObject):
    bundle_id = models.TextField(db_index=True, blank=True, null=True)
    bundle_name = models.TextField(db_index=True, blank=True, null=True)
    bundle_version = models.TextField(blank=True, null=True)
    bundle_version_str = models.TextField(blank=True, null=True)


class OSXAppInstance(AbstractMTObject):
    app = models.ForeignKey(OSXApp)
    bundle_path = models.TextField(blank=True, null=True)
    path = models.TextField(blank=True, null=True)
    sha_1 = models.CharField(max_length=40, blank=True, null=True)
    sha_256 = models.CharField(max_length=64, db_index=True, blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    signed_by = models.ForeignKey(Certificate, blank=True, null=True)


class TeamViewer(AbstractMTObject):
    teamviewer_id = models.TextField(blank=False, null=False)
    release = models.TextField(blank=True, null=True)
    unattended = models.NullBooleanField(blank=True, null=True)


class MachineSnapshotManager(MTObjectManager):
    def commit(self, tree):
        obj, created = super().commit(tree)
        if created:
            self.filter(source=obj.source,
                        machine__serial_number=obj.machine.serial_number,
                        mt_next__isnull=True).exclude(pk=obj.id).update(mt_next=obj)
        return obj, created

    def current(self):
        return self.select_related('machine',
                                   'business_unit',
                                   'os_version',
                                   'system_info').filter(mt_next__isnull=True)


class MachineSnapshot(AbstractMTObject):
    source = models.ForeignKey(Source)
    reference = models.TextField(blank=True, null=True)
    machine = models.ForeignKey(Machine)
    links = models.ManyToManyField(Link)
    business_unit = models.ForeignKey(BusinessUnit, blank=True, null=True)
    groups = models.ManyToManyField(MachineGroup)
    os_version = models.ForeignKey(OSVersion, blank=True, null=True)
    system_info = models.ForeignKey(SystemInfo, blank=True, null=True)
    osx_app_instances = models.ManyToManyField(OSXAppInstance)
    teamviewer = models.ForeignKey(TeamViewer, blank=True, null=True)
    mt_next = models.OneToOneField('self', blank=True, null=True, related_name="mt_previous")

    objects = MachineSnapshotManager()
    mt_excluded_fields = ('mt_next',)

    def update_diff(self):
        try:
            previous_snapshot = self.mt_previous
        except MachineSnapshot.DoesNotExist:
            return None
        else:
            return self.diff(previous_snapshot)

    def get_machine_str(self):
        if self.system_info and self.system_info.computer_name:
            return self.system_info.computer_name
        elif self.machine:
            return self.machine.serial_number
        elif self.reference:
            return self.reference
        else:
            return "{} #{}".format(self.source, self.id)

    def groups_with_links(self):
        for group in self.groups.prefetch_related('links', 'machine_links').all():
            ll = []
            for link in group.links.all():
                ll.append((link.url, link.anchor_text))
            for link in group.machine_links.all():
                url = link.url
                url = url.replace('%MACHINE_SNAPSHOT_REFERENCE%', self.reference)
                ll.append((url, link.anchor_text))
            yield group, ll
