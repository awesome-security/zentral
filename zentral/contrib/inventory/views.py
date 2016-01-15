from django.views import generic
from zentral.core.stores import frontend_store
from zentral.utils.text import str_to_ascii
from .models import BusinessUnit, MachineGroup, MachineSnapshot


class MachineListView(generic.TemplateView):
    template_name = "inventory/machine_list.html"

    @staticmethod
    def ms_dict_sorting_key(ms_list):
        key = None
        if not ms_list:
            return key
        ms = ms_list[0]
        key = str_to_ascii(ms.get_machine_str()).lower()
        return key

    def get_list_qs(self, **kwargs):
        return MachineSnapshot.objects.current()

    def get_list_title(self, **kwargs):
        return ""

    def get_context_data(self, **kwargs):
        context = super(MachineListView, self).get_context_data(**kwargs)
        context['inventory'] = True
        # group by machine serial number
        ms_dict = {}
        for ms in self.get_list_qs(**kwargs).order_by('system_info__computer_name'):
            ms_dict.setdefault(ms.machine.serial_number, []).append(ms)
        # sorted
        context['object_list'] = [(l[0].machine.serial_number,
                                   l[0].get_machine_str(),
                                   l) for l in sorted(ms_dict.values(),
                                                      key=self.ms_dict_sorting_key)]
        context['object_list_title'] = self.get_list_title(**kwargs)
        return context


class IndexView(MachineListView):
    pass


class GroupsView(generic.TemplateView):
    template_name = "inventory/group_list.html"

    def get_context_data(self, **kwargs):
        context = super(GroupsView, self).get_context_data(**kwargs)
        context['inventory'] = True
        context['object_list'] = MachineGroup.objects.current()
        return context


class GroupMachinesView(MachineListView):
    def get_list_qs(self, **kwargs):
        return MachineSnapshot.objects.current().filter(groups__id=kwargs['group_id'])

    def get_list_title(self, **kwargs):
        mg = MachineGroup.objects.select_related('source').get(pk=kwargs['group_id'])
        return "Group: {} - {}".format(mg.source.name, mg.name)


class BUView(generic.TemplateView):
    template_name = "inventory/bu_list.html"

    def get_context_data(self, **kwargs):
        context = super(BUView, self).get_context_data(**kwargs)
        context['inventory'] = True
        context['object_list'] = BusinessUnit.objects.current()
        return context


class BUMachinesView(MachineListView):
    def get_list_qs(self, **kwargs):
        return MachineSnapshot.objects.current().filter(business_unit__id=kwargs['bu_id'])

    def get_list_title(self, **kwargs):
        bu = BusinessUnit.objects.select_related('source').get(pk=kwargs['bu_id'])
        return "BU: {} - {}".format(bu.source.name, bu.name)


class MachineView(generic.TemplateView):
    template_name = "inventory/machine_detail.html"

    def get_context_data(self, **kwargs):
        context = super(MachineView, self).get_context_data(**kwargs)
        context['inventory'] = True
        # all current machine snapshots for this serial number
        ms_list = list(MachineSnapshot.objects.current().filter(machine__serial_number=context['serial_number']))
        # only the one with osx app infos
        osx_app_ms_list = [ms for ms in ms_list if ms.osx_app_instances.count()]
        for ms in ms_list:
            if ms.system_info and ms.system_info.computer_name:
                context['computer_name'] = ms.system_info.computer_name
                break
        context['ms_list'] = ms_list
        context['osx_app_ms_list'] = osx_app_ms_list
        return context


class MachineEventSet(object):
    def __init__(self, machine_serial_number, event_type=None):
        self.machine_serial_number = machine_serial_number
        self.event_type = event_type
        self.store = frontend_store
        self._count = None

    def count(self):
        if self._count is None:
            self._count = self.store.count(self.machine_serial_number, self.event_type)
        return self._count

    def __len__(self):
        return self.count()

    def __getitem__(self, k):
        if isinstance(k, slice):
            start = int(k.start or 0)
            stop = int(k.stop or start + 1)
        else:
            start = k
            stop = k + 1
        return self.store.fetch(self.machine_serial_number, start, stop - start, self.event_type)


class MachineEventsView(generic.ListView):
    template_name = "inventory/machine_events.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super(MachineEventsView, self).get_context_data(**kwargs)
        for ms in self.ms_list:
            context['serial_number'] = ms.machine.serial_number
            if ms.system_info and ms.system_info.computer_name:
                context['computer_name'] = ms.system_info.computer_name
                break

        # pagination
        page = context['page_obj']
        if page.has_next():
            qd = self.request.GET.copy()
            qd['page'] = page.next_page_number()
            context['next_url'] = "?{}".format(qd.urlencode())
        if page.has_previous():
            qd = self.request.GET.copy()
            qd['page'] = page.previous_page_number()
            context['previous_url'] = "?{}".format(qd.urlencode())
        event_types = []
        total_events = 0

        # event types selection
        request_event_type = self.request.GET.get('event_type')
        for event_type, count in frontend_store.event_types_with_usage(
                context['serial_number']).items():
            total_events += count
            event_types.append((event_type,
                                request_event_type == event_type,
                                "{} ({})".format(event_type.replace('_', ' ').title(), count)))
        event_types.sort()
        event_types.insert(0, ('',
                               request_event_type in [None, ''],
                               'All ({})'.format(total_events)))
        context['event_types'] = event_types
        return context

    def get_queryset(self):
        serial_number = self.kwargs['serial_number']
        self.ms_list = list(MachineSnapshot.objects.current().filter(machine__serial_number=serial_number))
        et = self.request.GET.get('event_type')
        return MachineEventSet(serial_number, et)
