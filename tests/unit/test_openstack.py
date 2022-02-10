import os
import tempfile

import mock

from tests.unit import utils

import core.plugins.openstack as openstack_core
from core import checks, known_bugs_utils
from core.ycheck.bugs import YBugChecker
from core.ycheck.configs import YConfigChecker
from core.ycheck.scenarios import YScenarioChecker
from core.issues import issue_types
from core.searchtools import FileSearcher
from plugins.openstack.pyparts import (
    vm_info,
    nova_external_events,
    service_info,
    service_network_checks,
    service_features,
    agent_event_checks,
    agent_exceptions,
)

OCTAVIA_UNIT_FILES = """
apache-htcacheclean.service               disabled       
apache-htcacheclean@.service              disabled       
apache2.service                           enabled        
apache2@.service                          disabled       
jujud-unit-octavia-0.service              enabled        
jujud-unit-octavia-hacluster-5.service    enabled        
octavia-api.service                       masked         
octavia-health-manager.service            enabled        
octavia-housekeeping.service              enabled        
octavia-worker.service                    enabled 
"""  # noqa

OCTAVIA_UNIT_FILES_APACHE_MASKED = """
apache-htcacheclean.service               disabled       
apache-htcacheclean@.service              disabled       
apache2.service                           masked        
apache2@.service                          disabled       
jujud-unit-octavia-0.service              enabled        
jujud-unit-octavia-hacluster-5.service    enabled        
octavia-api.service                       masked         
octavia-health-manager.service            enabled        
octavia-housekeeping.service              enabled        
octavia-worker.service                    enabled 
"""  # noqa


APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
[DEFAULT]
debug = True
"""

JOURNALCTL_OVS_CLEANUP_GOOD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_GOOD2 = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
May 04 10:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 10:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_BAD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
May 04 10:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 10:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

DPKG_L_MIX_RELS = """
ii  nova-common                          2:21.2.1-0ubuntu1                                    all          OpenStack Compute - common files
ii  neutron-common                       2:17.2.0-0ubuntu2                                    all          Neutron is a virtual network service for Openstack - common
"""  # noqa

LP_1929832 = r"""
2021-05-26 18:56:57.344 3457514 ERROR neutron.agent.l3.agent [-] Error while deleting router 8f14f808-c23a-422b-a3a8-7fb747e89676: neutron_lib.exceptions.ProcessExecutionError: Exit code: 99; Stdin: ; Stdout: ; Stderr: /usr/bin/neutron-rootwrap: Unauthorized command: kill -15 365134 (no filter matched)
"""  # noqa
LP_1896506 = r"""
Apr  6 06:36:09 kermath Keepalived_vrrp[23396]: Unknown configuration entry 'no_track' for ip address - ignoring
"""  # noqa
LP_1928031 = r"""
2021-08-26 05:47:20.754 1331249 ERROR neutron.agent.ovn.metadata.server AttributeError: 'MetadataProxyHandler' object has no attribute 'sb_idl'
"""  # noqa

EVENT_PCIDEVNOTFOUND_LOG = r"""
2021-09-17 13:49:47.257 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:10.0: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:10.0 not found
2021-09-17 13:49:47.609 3060998 WARNING nova.pci.utils [req-f6448047-9a0f-453b-9189-079dd00ab3a3 - - - - -] No net device was found for VF 0000:3b:0f.7: nova.exception.PciDeviceNotFoundById: PCI device 0000:3b:0f.7 not found
"""  # noqa

EVENT_APACHE_CONN_REFUSED_LOG = r"""
[Tue Oct 26 17:27:20.477742 2021] [proxy:error] [pid 29484:tid 140230740928256] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:29:22.338485 2021] [proxy:error] [pid 29485:tid 140231076472576] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
[Tue Oct 26 17:31:18.143966 2021] [proxy:error] [pid 29485:tid 140231219083008] (111)Connection refused: AH00957: HTTP: attempt to connect to 127.0.0.1:8981 (localhost) failed
"""  # noqa

EVENT_OCTAVIA_CHECKS = r"""
2021-03-09 14:53:04.467 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ac9849a2-f81e-4578-aedf-3637420c97ff', 'load_balancer_id': '7a3b90ed-020e-48f0-ad6f-b28443fa2277', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe6c:2963', 'compute_id': 'af04050e-b845-4bca-9e61-ded03039d2c6', 'role': 'master_or_backup'}
2021-03-09 17:44:37.379 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': '0cd68e26-abb7-4e6b-8272-5ccf017b6de7', 'load_balancer_id': '9cd90142-5501-4362-93ef-1ad219baf45a', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:feae:514c', 'compute_id': '314e4b2f-9c64-41c9-b337-7d0229127d48', 'role': 'master_or_backup'}
2021-03-09 18:19:10.369 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'ddaf13ec-858f-42d1-bdc8-d8b529c7c524', 'load_balancer_id': 'e9cb98af-9c21-4cf6-9661-709179ce5733', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe2f:9d58', 'compute_id': 'c71c5eca-c862-49dd-921c-273e51dfb574', 'role': 'master_or_backup'}
2021-03-09 20:01:46.376 9684 INFO octavia.controller.worker.v1.flows.amphora_flows [-] Performing failover for amphora: {'id': 'bbf6107b-86b5-45f5-ace1-e077871860ac', 'load_balancer_id': '98aefcff-60e5-4087-8ca6-5087ae970440', 'lb_network_ip': 'fc00:1f77:9de0:cd56:f816:3eff:fe5b:4afb', 'compute_id': '54061176-61c8-4915-b896-e026c3eeb60f', 'role': 'master_or_backup'}

2021-06-01 23:25:39.223 43076 WARNING octavia.controller.healthmanager.health_drivers.update_db [-] Amphora 3604bf2a-ee51-4135-97e2-ec08ed9321db health message was processed too slowly: 10.550589084625244s! The system may be overloaded or otherwise malfunctioning. This heartbeat has been ignored and no update was made to the amphora health entry. THIS IS NOT GOOD.
"""  # noqa


class TestOpenstackBase(utils.BaseTestCase):

    IP_LINK_SHOW = None

    def fake_ip_link_w_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(10000000, 100000000)
        return [line + '\n' for line in lines.split('\n')]

    def fake_ip_link_no_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(0, 0)
        return [line + '\n' for line in lines.split('\n')]

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ["PLUGIN_NAME"] = "openstack"

        if self.IP_LINK_SHOW is None:
            path = os.path.join(os.environ['DATA_ROOT'],
                                "sos_commands/networking/ip_-s_-d_link")
            with open(path) as fd:
                self.IP_LINK_SHOW = fd.readlines()


class TestOpenstackPluginCore(TestOpenstackBase):

    def test_release_name(self):
        base = openstack_core.OpenstackBase()
        self.assertEqual(base.release_name, 'ussuri')

    @mock.patch.object(openstack_core.issue_utils, 'add_issue')
    def test_release_name_detect_multiples(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        with mock.patch.object(checks, 'CLIHelper') as mock_cli:
            mock_cli.return_value = mock.MagicMock()
            mock_cli.return_value.dpkg_l.return_value = \
                ["{}\n".format(line) for line in DPKG_L_MIX_RELS.split('\n')]

            mock_add_issue.side_effect = fake_add_issue
            base = openstack_core.OpenstackBase()
            self.assertEqual(base.release_name, 'ussuri')
            self.assertEqual(len(issues), 1)
            self.assertEqual(type(issues[0]), issue_types.OpenstackWarning)
            msg = ("openstack packages from mixed releases found - ['ussuri', "
                   "'victoria']")
            self.assertEqual(issues[0].msg, msg)


class TestOpenstackServiceInfo(TestOpenstackBase):

    def test_get_service_info(self):
        expected = {'systemd': {
                        'enabled': [
                            'haproxy',
                            'keepalived',
                            'neutron-dhcp-agent',
                            'neutron-l3-agent',
                            'neutron-metadata-agent',
                            'neutron-openvswitch-agent',
                            'neutron-ovs-cleanup',
                            'nova-api-metadata',
                            'nova-compute'],
                        'disabled': ['radvd'],
                        'indirect': ['vaultlocker-decrypt']},
                    'ps': [
                        'apache2 (6)',
                        'dnsmasq (1)',
                        'haproxy (7)',
                        'keepalived (2)',
                        'mysqld (1)',
                        'neutron-dhcp-agent (1)',
                        'neutron-keepalived-state-change (2)',
                        'neutron-l3-agent (1)',
                        'neutron-metadata-agent (5)',
                        'neutron-openvswitch-agent (1)',
                        'nova-api-metadata (5)',
                        'nova-compute (1)',
                        'qemu-system-x86_64 (1)',
                        'vault (1)']}
        inst = service_info.OpenstackInfo()
        inst()
        self.assertEqual(inst.output["services"], expected)

    @mock.patch.object(service_info.issue_utils, 'add_issue')
    @mock.patch('core.checks.CLIHelper')
    def test_get_service_info_apache_service(self, mock_helper,
                                             mock_add_issue):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.systemctl_list_unit_files.return_value = \
            OCTAVIA_UNIT_FILES.splitlines(keepends=True)
        expected = {'enabled': [
                        'apache2',
                        'octavia-health-manager',
                        'octavia-housekeeping',
                        'octavia-worker'],
                    'masked': [
                        'octavia-api']
                    }
        with mock.patch.object(service_info.OpenstackServiceChecksBase,
                               'openstack_installed', lambda: True):
            inst = service_info.OpenstackInfo()
            inst()
            self.assertEqual(inst.output['services']['systemd'], expected)

        self.assertFalse(mock_add_issue.called)

    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch.object(openstack_core, "APT_SOURCE_PATH",
                                   dtmp):
                inst = service_info.OpenstackInfo()
                inst()
                self.assertEqual(inst.output["release"], "ussuri")

    def test_get_debug_log_info(self):
        expected = {'neutron': True, 'nova': True}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            os.environ["DATA_ROOT"] = dtmp
            inst = service_info.OpenstackInfo()
            # fake some core packages
            inst.apt_check._core_packages = {"foo": 1}
            inst()
            self.assertEqual(inst.output["debug-logging-enabled"],
                             expected)

    def test_get_pkg_info(self):
        expected = [
            'conntrack 1:1.4.5-2',
            'dnsmasq-base 2.80-1.1ubuntu1.4',
            'dnsmasq-utils 2.80-1.1ubuntu1.4',
            'haproxy 2.0.13-2ubuntu0.3',
            'keepalived 1:2.0.19-2ubuntu0.1',
            'keystone-common 2:17.0.1-0ubuntu1',
            'libvirt-daemon 6.0.0-0ubuntu8.15',
            'libvirt-daemon-driver-qemu 6.0.0-0ubuntu8.15',
            'libvirt-daemon-driver-storage-rbd 6.0.0-0ubuntu8.15',
            'libvirt-daemon-system 6.0.0-0ubuntu8.15',
            'libvirt-daemon-system-systemd 6.0.0-0ubuntu8.15',
            'mysql-common 5.8+1.0.5ubuntu2',
            'neutron-common 2:16.4.1-0ubuntu2',
            'neutron-dhcp-agent 2:16.4.1-0ubuntu2',
            'neutron-fwaas-common 1:16.0.0-0ubuntu0.20.04.1',
            'neutron-l3-agent 2:16.4.1-0ubuntu2',
            'neutron-metadata-agent 2:16.4.1-0ubuntu2',
            'neutron-openvswitch-agent 2:16.4.1-0ubuntu2',
            'nova-api-metadata 2:21.2.3-0ubuntu1',
            'nova-common 2:21.2.3-0ubuntu1',
            'nova-compute 2:21.2.3-0ubuntu1',
            'nova-compute-kvm 2:21.2.3-0ubuntu1',
            'nova-compute-libvirt 2:21.2.3-0ubuntu1',
            'python3-barbicanclient 4.10.0-0ubuntu1',
            'python3-cinderclient 1:7.0.0-0ubuntu1',
            'python3-designateclient 2.11.0-0ubuntu2',
            'python3-glanceclient 1:3.1.1-0ubuntu1',
            'python3-keystone 2:17.0.1-0ubuntu1',
            'python3-keystoneauth1 4.0.0-0ubuntu1',
            'python3-keystoneclient 1:4.0.0-0ubuntu1',
            'python3-keystonemiddleware 9.0.0-0ubuntu1',
            'python3-neutron 2:16.4.1-0ubuntu2',
            'python3-neutron-fwaas 1:16.0.0-0ubuntu0.20.04.1',
            'python3-neutron-lib 2.3.0-0ubuntu1',
            'python3-neutronclient 1:7.1.1-0ubuntu1',
            'python3-nova 2:21.2.3-0ubuntu1',
            'python3-novaclient 2:17.0.0-0ubuntu1',
            'python3-oslo.cache 2.3.0-0ubuntu1',
            'python3-oslo.concurrency 4.0.2-0ubuntu1',
            'python3-oslo.config 1:8.0.2-0ubuntu1',
            'python3-oslo.context 1:3.0.2-0ubuntu1',
            'python3-oslo.db 8.1.0-0ubuntu1',
            'python3-oslo.i18n 4.0.1-0ubuntu1',
            'python3-oslo.log 4.1.1-0ubuntu1',
            'python3-oslo.messaging 12.1.6-0ubuntu1',
            'python3-oslo.middleware 4.0.2-0ubuntu1',
            'python3-oslo.policy 3.1.0-0ubuntu1.1',
            'python3-oslo.privsep 2.1.1-0ubuntu1',
            'python3-oslo.reports 2.0.1-0ubuntu1',
            'python3-oslo.rootwrap 6.0.2-0ubuntu1',
            'python3-oslo.serialization 3.1.1-0ubuntu1',
            'python3-oslo.service 2.1.1-0ubuntu1.1',
            'python3-oslo.upgradecheck 1.0.1-0ubuntu1',
            'python3-oslo.utils 4.1.1-0ubuntu1',
            'python3-oslo.versionedobjects 2.0.1-0ubuntu1',
            'python3-oslo.vmware 3.3.1-0ubuntu1',
            'qemu-kvm 1:4.2-3ubuntu6.19',
            'radvd 1:2.17-2'
            ]
        inst = service_info.OpenstackPackageChecks()
        inst()
        self.assertEquals(inst.output["dpkg"], expected)

    @mock.patch.object(service_info, 'CLIHelper')
    @mock.patch.object(service_info.issue_utils, "add_issue")
    def test_run_service_info(self, mock_add_issue, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD.splitlines(keepends=True)
        inst = service_info.NeutronServiceChecks()
        inst()
        self.assertFalse(mock_add_issue.called)

    @mock.patch.object(service_info, 'CLIHelper')
    @mock.patch.object(service_info.issue_utils, "add_issue")
    def test_run_service_info2(self, mock_add_issue, mock_helper):
        """
        Covers scenario where we had manual restart but not after last reboot.
        """
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD2.splitlines(keepends=True)
        inst = service_info.NeutronServiceChecks()
        inst()
        self.assertFalse(mock_add_issue.called)

    @mock.patch.object(service_info, 'CLIHelper')
    @mock.patch.object(service_info.issue_utils, "add_issue")
    def test_run_service_info_w_issue(self, mock_add_issue, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        inst = service_info.NeutronServiceChecks()
        inst()
        self.assertTrue(mock_add_issue.called)

    def test_get_neutronl3ha_info(self):
        expected = {'neutron-l3ha': {'backup':
                                     ['984c22fd-64b3-4fa1-8ddd-87090f401ce5']}}
        inst = service_info.NeutronL3HAInfo()
        inst()
        self.assertEquals(inst.output, expected)


class TestOpenstackVmInfo(TestOpenstackBase):

    def test_get_vm_checks(self):
        expected = {"vm-info": {
                        "running": ['d1d75e2f-ada4-49bc-a963-528d89dfda25'],
                        "vcpu-info": {
                            "available-cores": 2,
                            "system-cores": 2,
                            "smt": False,
                            "used": 1,
                            "overcommit-factor": 0.5,
                            }
                        }
                    }
        inst = vm_info.OpenstackInstanceChecks()
        inst()
        self.assertEquals(inst.output, expected)

    def test_vm_migration_analysis(self):
        expected = {'nova-migrations': {
                        'live-migration': {
                            '359150c9-6f40-416e-b381-185bff09e974': [
                                {'start': '2022-02-10 16:18:28',
                                 'end': '2022-02-10 16:18:28',
                                 'duration': 0.0,
                                 'regressions': {
                                     'memory': 0,
                                     'disk': 0},
                                 'iterations': 1}]
                        }}}
        inst = vm_info.NovaServerMigrationAnalysis()
        inst()
        self.assertEquals(inst.output, expected)


class TestOpenstackNovaExternalEvents(TestOpenstackBase):

    def test_get_events(self):
        inst = nova_external_events.NovaExternalEventChecks()
        inst()
        events = {'network-changed':
                  {"succeeded":
                   [{"port": "6a0486f9-823b-4dcf-91fb-8a4663d31855",
                     "instance": "359150c9-6f40-416e-b381-185bff09e974"}]},
                  'network-vif-plugged':
                  {"succeeded":
                   [{"instance": '359150c9-6f40-416e-b381-185bff09e974',
                     "port": "6a0486f9-823b-4dcf-91fb-8a4663d31855"}]}}
        self.assertEquals(inst.output["os-server-external-events"], events)


class TestOpenstackServiceNetworkChecks(TestOpenstackBase):

    def test_get_ns_info(self):
        ns_info = {'namespaces': {'qrouter': 1, 'fip': 1,
                                  'snat': 1}}
        inst = service_network_checks.OpenstackNetworkChecks()
        inst.get_ns_info()
        self.assertEqual(inst.output["network"], ns_info)

    @mock.patch.object(service_network_checks, 'CLIHelper')
    def test_get_ns_info_none(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ip_link.return_value = []
        inst = service_network_checks.OpenstackNetworkChecks()
        inst.get_ns_info()
        self.assertEqual(inst.output, None)

    def test_get_network_checker(self):
        expected = {
            'config': {
                'nova': {
                    'my_ip': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}},
                    'live_migration_inbound_addr': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}}},
                'neutron': {'local_ip': {
                    'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'state': 'UP',
                        'speed': 'unknown'}}}
            },
            'namespaces': {
                'fip': 1,
                'qrouter': 1,
                'snat': 1
            },
        }
        inst = service_network_checks.OpenstackNetworkChecks()
        inst()
        self.assertEqual(inst.output["network"], expected)


class TestOpenstackServiceFeatures(TestOpenstackBase):

    def test_get_service_features(self):
        inst = service_features.ServiceFeatureChecks()
        inst.get_service_features()
        expected = {'neutron': {'dhcp-agent': {
                                    'enable_isolated_metadata': True,
                                    'enable_metadata_network': True,
                                    'ovs_use_veth': False},
                                'l3-agent': {
                                    'agent_mode': 'dvr_snat'},
                                'main': {
                                    'availability_zone': 'nova'},
                                'openvswitch-agent': {
                                    'l2_population': True,
                                    'firewall_driver': 'openvswitch'}},
                    'nova': {'main': {
                                'live_migration_permit_auto_converge': False,
                                'live_migration_permit_post_copy': False}}}
        self.assertEqual(inst.output["features"], expected)


class TestOpenstackCPUPinning(TestOpenstackBase):

    def test_cores_to_list(self):
        ret = checks.ConfigBase.expand_value_ranges("0-4,8,9,28-32")
        self.assertEqual(ret, [0, 1, 2, 3, 4, 8, 9, 28, 29, 30, 31, 32])

    @mock.patch('core.plugins.system.NUMAInfo.nodes',
                {0: [1, 3, 5], 1: [0, 2, 4]})
    @mock.patch('core.plugins.system.SystemBase.num_cpus', 16)
    @mock.patch('core.plugins.kernel.KernelConfig.get',
                lambda *args, **kwargs: range(9, 16))
    @mock.patch('core.plugins.kernel.SystemdConfig.get',
                lambda *args, **kwargs: range(2, 9))
    def test_nova_pinning_base(self):
        with mock.patch('core.plugins.openstack.NovaCPUPinning.vcpu_pin_set',
                        [0, 1, 2]):
            inst = openstack_core.NovaCPUPinning()
            self.assertEquals(inst.cpu_dedicated_set_name, 'vcpu_pin_set')

        inst = openstack_core.NovaCPUPinning()
        self.assertEquals(inst.cpu_shared_set, [])
        self.assertEquals(inst.cpu_dedicated_set, [])
        self.assertEquals(inst.vcpu_pin_set, [])
        self.assertEquals(inst.cpu_dedicated_set_name, 'cpu_dedicated_set')
        self.assertEquals(inst.cpu_dedicated_set_intersection_isolcpus, [])
        self.assertEquals(inst.cpu_dedicated_set_intersection_cpuaffinity, [])
        self.assertEquals(inst.cpu_shared_set_intersection_isolcpus, [])
        self.assertEquals(inst.cpuaffinity_intersection_isolcpus, [])
        self.assertEquals(inst.unpinned_cpus_pcent, 12)
        self.assertEquals(inst.num_unpinned_cpus, 2)
        self.assertEquals(inst.nova_pinning_from_multi_numa_nodes, False)
        with mock.patch('core.plugins.openstack.NovaCPUPinning.'
                        'cpu_dedicated_set', [0, 1, 4]):
            self.assertEquals(inst.nova_pinning_from_multi_numa_nodes, True)


class TestOpenstackAgentEventChecks(TestOpenstackBase):

    def test_process_rpc_loop_results(self):
        expected = {'rpc-loop': {
                        'stats': {
                            'avg': 0.0,
                            'max': 0.02,
                            'min': 0.0,
                            'samples': 2500,
                            'stdev': 0.0},
                        'top': {
                            '2100': {
                                'duration': 0.01,
                                'end': '2022-02-10 00:00:19.864000',
                                'start': '2022-02-10 00:00:19.854000'},
                            '2101': {
                                'duration': 0.01,
                                'end': '2022-02-10 00:00:21.867000',
                                'start': '2022-02-10 00:00:21.856000'},
                            '3152': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:35:24.916000',
                                'start': '2022-02-10 00:35:24.896000'},
                            '3302': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:40:25.068000',
                                'start': '2022-02-10 00:40:25.051000'},
                            '3693': {
                                'duration': 0.02,
                                'end': '2022-02-10 00:53:27.452000',
                                'start': '2022-02-10 00:53:27.434000'}}}}

        section_key = "neutron-ovs-agent"
        c = agent_event_checks.NeutronAgentEventChecks(
                                                      searchobj=FileSearcher())
        c()
        self.assertEqual(c.output.get(section_key), expected)

    def test_get_router_event_stats(self):
        expected = {'router-spawn-events': {
                        'stats': {
                            'avg': 578.02,
                            'max': 578.02,
                            'min': 578.02,
                            'samples': 1,
                            'stdev': 0.0},
                        'top': {
                            '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                                'duration': 578.02,
                                'end': '2022-02-10 '
                                       '16:19:00.697000',
                                'start': '2022-02-10 '
                                         '16:09:22.679000'}}},
                    'router-updates': {
                        'stats': {
                            'avg': 28.29,
                            'max': 63.39,
                            'min': 12.96,
                            'samples': 10,
                            'stdev': 16.18},
                        'top': {
                            '964fd5e1-430e-4102-91a4-a0f2930f89b6': {
                                'duration': 22.37,
                                'end': '2022-02-10 16:14:07.813000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:13:45.442000'},
                            '96a22135-d383-4546-a385-cb683166c7d4': {
                                'duration': 33.41,
                                'end': '2022-02-10 16:10:35.710000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:10:02.303000'},
                            '97310a6f-5261-45d2-9e3b-1dcfeb534886': {
                                'duration': 63.39,
                                'end': '2022-02-10 16:10:02.302000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:08:58.916000'},
                            'b259b6d5-5ef3-4ed6-964d-a7f648a0b1f4': {
                                'duration': 31.44,
                                'end': '2022-02-10 16:13:45.440000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:13:13.997000'},
                            'b7eb99ad-b5d3-4e82-9ce8-47c66f014b77': {
                                'duration': 51.71,
                                'end': '2022-02-10 16:11:27.417000',
                                'router':
                                    '984c22fd-64b3-4fa1-8ddd-87090f401ce5',
                                'start': '2022-02-10 16:10:35.711000'}}}}

        section_key = "neutron-l3-agent"
        c = agent_event_checks.NeutronAgentEventChecks(
                                                      searchobj=FileSearcher())
        c()
        self.assertEqual(c.output.get(section_key), expected)

    @mock.patch.object(agent_event_checks, "NeutronAgentEventChecks")
    def test_run_agent_event_checks(self, mock_agent_event_checks):
        agent_event_checks.AgentEventChecks()()
        self.assertTrue(mock_agent_event_checks.called)

    def test_run_octavia_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, ('var/log/octavia/'
                                          'octavia-health-manager.log'))
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_OCTAVIA_CHECKS)

            expected = {'amp-missed-heartbeats': {
                         '2021-06-01': {
                          '3604bf2a-ee51-4135-97e2-ec08ed9321db': 1,
                          }},
                        'lb-failovers': {
                         'auto': {
                          '2021-03-09': {
                              '7a3b90ed-020e-48f0-ad6f-b28443fa2277': 1,
                              '98aefcff-60e5-4087-8ca6-5087ae970440': 1,
                              '9cd90142-5501-4362-93ef-1ad219baf45a': 1,
                              'e9cb98af-9c21-4cf6-9661-709179ce5733': 1,
                            }
                          }
                         }
                        }
            for section_key in ["octavia-worker", "octavia-health-manager"]:
                sobj = FileSearcher()
                c = agent_event_checks.OctaviaAgentEventChecks(searchobj=sobj)
                c()
                self.assertEqual(c.output["octavia"].get(section_key),
                                 expected.get(section_key))

    def test_run_apache_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/apache2/error.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_APACHE_CONN_REFUSED_LOG)

            expected = {'connection-refused': {
                            '2021-10-26': {'127.0.0.1:8981': 3}}}
            for section_key in ['connection-refused']:
                sobj = FileSearcher()
                c = agent_event_checks.ApacheEventChecks(searchobj=sobj)
                c()
                self.assertEqual(c.output['apache'].get(section_key),
                                 expected.get(section_key))

    def test_run_nova_checks(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/nova/nova-compute.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENT_PCIDEVNOTFOUND_LOG)

            expected = {'PciDeviceNotFoundById': {
                            '2021-09-17': {'0000:3b:0f.7': 1,
                                           '0000:3b:10.0': 1}}}
            sobj = FileSearcher()
            c = agent_event_checks.NovaAgentEventChecks(searchobj=sobj)
            c()
            self.assertEqual(c.output["nova"], expected)

    def test_run_neutron_l3ha_checks(self):
        expected = {'keepalived': {
                     'transitions': {
                      '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                          '2022-02-10': 1}}}}
        sobj = FileSearcher()
        inst = agent_event_checks.NeutronL3HAEventChecks(searchobj=sobj)
        inst()
        self.assertEqual(inst.output["neutron-l3ha"], expected)

    @mock.patch.object(agent_event_checks.issue_utils, "add_issue")
    @mock.patch.object(agent_event_checks, "VRRP_TRANSITION_WARN_THRESHOLD", 0)
    def test_run_neutron_l3ha_checks_w_issue(self, mock_add_issue):
        os.environ["USE_ALL_LOGS"] = "False"
        expected = {'keepalived': {
                     'transitions': {
                      '984c22fd-64b3-4fa1-8ddd-87090f401ce5': {
                       '2022-02-10': 1}}}}
        sobj = FileSearcher()
        inst = agent_event_checks.NeutronL3HAEventChecks(searchobj=sobj)
        inst()
        self.assertEqual(inst.output["neutron-l3ha"], expected)
        self.assertTrue(mock_add_issue.called)


class TestOpenstackAgentExceptions(TestOpenstackBase):

    def test_get_agent_exceptions(self):
        neutron_expected = {
            'neutron-openvswitch-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 88,
                    '2022-02-09': 9
                    }},
            'neutron-dhcp-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 126,
                    '2022-02-09': 18
                    }},
            'neutron-l3-agent': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 82,
                    '2022-02-09': 9
                    }}}

        nova_expected = {
            'nova-compute': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 123,
                    '2022-02-09': 3,
                    },
                'nova.exception.ResourceProviderRetrievalFailed': {
                    '2022-02-04': 6
                    },
                'nova.exception.ResourceProviderAllocationRetrievalFailed': {
                    '2022-02-04': 2
                    }},
            'nova-api-metadata': {
                'oslo_messaging.exceptions.MessagingTimeout': {
                    '2022-02-04': 110,
                    '2022-02-09': 56}}}

        expected = {"nova": nova_expected, "neutron": neutron_expected}
        inst = agent_exceptions.AgentExceptionChecks()
        inst()
        self.assertEqual(inst.output['agent-exceptions'], expected)


class TestOpenstackConfigChecks(TestOpenstackBase):

    @mock.patch('core.issues.issue_utils.add_issue')
    def test_config_checks_no_issue(self, mock_add_issue):
        YConfigChecker()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('nova-dpdk.yaml'))
    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.issues.issue_utils.add_issue')
    @mock.patch('core.plugins.openstack.OpenstackChecksBase.plugin_runnable',
                True)
    def test_nova_dpdk(self, mock_add_issue, mock_helper):
        issues = []

        def fake_add_issue(issue):
            issues.append(type(issue))

        mock_add_issue.side_effect = fake_add_issue
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii  openvswitch-switch-dpdk 2.13.3-0ubuntu0.20.04.2 amd64"]
        # no need to mock the config since the fact it doesnt exist will
        # trigger the alert.
        YConfigChecker()()
        self.assertTrue(mock_add_issue.called)
        self.assertEquals(issues, [issue_types.OpenstackWarning])


class TestOpenstackBugChecks(TestOpenstackBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron-l3-agent.yaml'))
    def test_1929832(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp,
                                   'var/log/neutron/neutron-l3-agent.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1929832)

            YBugChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1929832',
                          'desc': ('known neutron l3-agent bug identified '
                                   'that impacts deletion of neutron '
                                   'routers.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron-l3-agent.yaml'))
    def test_1896506(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/syslog')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1896506)

            YBugChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1896506',
                          'desc': ('known neutron l3-agent bug identified '
                                   'that critically impacts keepalived.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron.yaml'))
    def test_1928031(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(
                        dtmp, 'var/log/neutron/neutron-ovn-metadata-agent.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP_1928031)

            YBugChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1928031',
                          'desc': ('known neutron-ovn bug identified that '
                                   'impacts OVN sbdb connections.'),
                          'origin': 'openstack.01part'}]}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('neutron.yaml'))
    def test_1927868(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii neutron-common 2:16.4.0-0ubuntu2 all"]

        YBugChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1927868',
                      'desc': ("installed package 'neutron-common' with "
                               "version 2:16.4.0-0ubuntu2 has a known "
                               "critical bug. If this environment is "
                               "using Neutron ML2 OVS (i.e. not OVN) it "
                               "should be upgraded asap."),
                      'origin': 'openstack.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)


class TestOpenstackScenarioChecks(TestOpenstackBase):

    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenarios_none(self, mock_add_issue):
        YScenarioChecker()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('core.plugins.openstack.OpenstackChecksBase.plugin_runnable',
                True)
    @mock.patch('core.plugins.kernel.CPU.cpufreq_scaling_governor_all',
                'powersave')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenarios_cpufreq(self, mock_add_issue):
        issues = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in issues.values()]), 1)
        self.assertTrue(issue_types.OpenstackWarning in issues)
        self.assertTrue('not using cpufreq scaling_governor in "performance" '
                        'mode' in issues[issue_types.OpenstackWarning][0])

    @mock.patch('core.plugins.system.NUMAInfo.nodes',
                {0: [1, 3, 5], 1: [0, 2, 4]})
    @mock.patch('core.plugins.openstack.OpenstackConfig')
    @mock.patch('core.plugins.openstack.OpenstackChecksBase.release_name',
                'train')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenario_pinning_invalid_config(self, mock_add_issue,
                                             mock_config):
        issues = {}
        config = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue

        def fake_get(key, **_kwargs):
            return config.get(key)

        mock_config.return_value = mock.MagicMock()
        mock_config.return_value.get.side_effect = fake_get

        config = {'vcpu_pin_set': [1, 2, 3],
                  'cpu_dedicated_set': [1, 2, 3]}
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in issues.values()]), 2)
        msg = ("Nova config options 'vcpu_pin_set' and "
               "'cpu_dedicated_set' are both set/configured which is not "
               "allowed for >= Train.")
        self.assertEqual(issues[issue_types.OpenstackError], [msg])
        msg = ("Nova config option 'vcpu_pin_set' is configured with "
               "cores from more than one numa node. This can have "
               "performance implications and should be checked.")
        self.assertEqual(issues[issue_types.OpenstackWarning], [msg])

        config = {'cpu_dedicated_set': [1, 2, 3]}
        issues = {}
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in issues.values()]), 1)
        msg = ("Nova config option 'cpu_dedicated_set' is configured with "
               "cores from more than one numa node. This can have "
               "performance implications and should be checked.")
        self.assertEqual(issues[issue_types.OpenstackWarning], [msg])

        config = {'vcpu_pin_set': [1, 2, 3]}
        issues = {}
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in issues.values()]), 2)
        msg1 = ("Nova config option 'vcpu_pin_set' is configured with "
                "cores from more than one numa node. This can have "
                "performance implications and should be checked.")
        msg2 = ("Nova config option 'vcpu_pin_set' is configured yet it "
                "is deprecated as of the Train release and may be "
                "ignored. Recommendation is to switch to using "
                "cpu_dedicated_set and/or cpu_shared_set (see upstream "
                "docs).")
        self.assertEqual(sorted(issues[issue_types.OpenstackWarning]),
                         sorted([msg1, msg2]))

    @mock.patch('core.plugins.openstack.OpenstackChecksBase.plugin_runnable',
                True)
    @mock.patch('core.issues.issue_utils.add_issue')
    @mock.patch('core.checks.CLIHelper')
    def test_scenario_masked_services(self, mock_helper, mock_add_issue):
        issues = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.systemctl_list_unit_files.return_value = \
            OCTAVIA_UNIT_FILES_APACHE_MASKED.splitlines(keepends=True)
        YScenarioChecker()()
        self.assertEqual(sum([len(msgs) for msgs in issues.values()]), 1)
        self.assertTrue(issue_types.OpenstackWarning in issues)
        self.assertTrue("masked: apache2" in
                        issues[issue_types.OpenstackWarning][0])
