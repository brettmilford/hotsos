import os
import shutil
import tempfile

import mock

from tests.unit import utils

from core.ycheck.bugs import YBugChecker
from core.ycheck.scenarios import YScenarioChecker
from core.issues.issue_types import SystemWarning
from core.plugins.system import NUMAInfo
from plugins.system.pyparts import (
    checks,
    general,
)

NUMACTL = """
available: 2 nodes (0-1)
node 0 cpus: 0 2 4 6 8 10 12 14 16 18 20 22 24 26 28 30 32 34 36 38
node 0 size: 96640 MB
node 0 free: 72733 MB
node 1 cpus: 1 3 5 7 9 11 13 15 17 19 21 23 25 27 29 31 33 35 37 39
node 1 size: 96762 MB
node 1 free: 67025 MB
node distances:
node   0   1 
  0:  10  21 
  1:  21  10
""".splitlines(keepends=True)  # noqa


class SystemTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'system'


class TestSystemGeneral(SystemTestsBase):

    def test_get_service_info(self):
        expected = {'date': 'Thu Feb 10 16:19:17 UTC 2022',
                    'load': '3.58, 3.27, 2.58',
                    'hostname': 'compute4',
                    'num-cpus': 2,
                    'os': 'ubuntu focal',
                    'rootfs': ('/dev/vda2      308585260 25514372 267326276 '
                               '  9% /'),
                    'virtualisation': 'kvm',
                    'unattended-upgrades': 'ENABLED'}
        inst = general.SystemGeneral()
        inst()
        self.assertEqual(inst.output, expected)


class TestNUMAInfo(SystemTestsBase):

    @mock.patch('core.plugins.system.CLIHelper')
    def test_numainfo(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.numactl.return_value = NUMACTL
        nodes = {0: [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                     32, 34, 36, 38],
                 1: [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31,
                     33, 35, 37, 39]}
        info = NUMAInfo()
        self.assertEqual(info.nodes, nodes)
        self.assertEqual(info.cores(0), nodes[0])
        self.assertEqual(info.cores(1), nodes[1])
        self.assertEqual(info.cores(), nodes[0] + nodes[1])


class TestSystemChecks(SystemTestsBase):

    def test_sysctl_checks(self):
        expected = {'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        inst = checks.SystemChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_sysctl_checks_w_issue(self):
        expected = {'sysctl-mismatch': {
                        'kernel.pid_max': {
                            'actual': '4194304',
                            'expected': '12345678'}},
                    'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        with tempfile.TemporaryDirectory() as dtmp:
            orig_data_root = os.environ['DATA_ROOT']
            os.environ['DATA_ROOT'] = dtmp
            os.makedirs(os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(orig_data_root, 'etc/sysctl.conf')
            etc_sysctl_d = os.path.join(orig_data_root, 'etc/sysctl.d')
            shutil.copy(etc_sysctl_conf, os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(dtmp, 'etc/sysctl.conf')
            shutil.copytree(etc_sysctl_d, os.path.join(dtmp, 'etc/sysctl.d'))
            shutil.copytree(os.path.join(orig_data_root, 'usr/lib/sysctl.d'),
                            os.path.join(dtmp, 'usr/lib/sysctl.d'))
            os.makedirs(os.path.join(dtmp, 'sos_commands'))
            shutil.copytree(os.path.join(orig_data_root,
                                         'sos_commands/kernel'),
                            os.path.join(dtmp, 'sos_commands/kernel'))

            with open(etc_sysctl_conf, 'a') as fd:
                fd.write('-net.core.rmem_default\n')

            # create a config with an unsetter
            with open(os.path.join(dtmp, 'etc/sysctl.d/99-unit-test.conf'),
                      'w') as fd:
                fd.write("-net.ipv4.conf.all.rp_filter\n")

            # create a config that has not been applied
            with open(os.path.join(dtmp, 'etc/sysctl.d/98-unit-test.conf'),
                      'w') as fd:
                fd.write("kernel.pid_max = 12345678\n")
                fd.write("net.ipv4.conf.all.rp_filter = 200\n")

            # inject an unset value into an invalid file
            with open(os.path.join(dtmp, 'etc/sysctl.d/97-unit-test.conf.bak'),
                      'w') as fd:
                fd.write("kernel.watchdog = 0\n")

            # create a config with an unsetter that wont be applied since it
            # has a lesser priority.
            with open(os.path.join(dtmp, 'etc/sysctl.d/96-unit-test.conf'),
                      'w') as fd:
                fd.write("-kernel.pid_max\n")
                fd.write("net.core.rmem_default = 1000000000\n")

            inst = checks.SystemChecks()
            inst()
            self.assertEqual(inst.output, expected)


class TestSystemBugChecks(SystemTestsBase):

    @mock.patch('core.ycheck.bugs.add_known_bug')
    def test_bug_checks(self, mock_add_known_bug):
        bugs = []

        def fake_add_bug(*args, **kwargs):
            bugs.append((args, kwargs))

        mock_add_known_bug.side_effect = fake_add_bug
        YBugChecker()()
        # This will need modifying once we have some storage bugs defined
        self.assertFalse(mock_add_known_bug.called)
        self.assertEqual(len(bugs), 0)


class TestSystemScenarioChecks(SystemTestsBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('unattended_upgrades.yaml'))
    @mock.patch('core.plugins.system.SystemBase.unattended_upgrades_enabled',
                True)
    @mock.patch('core.plugins.system.SystemChecksBase.plugin_runnable',
                True)
    @mock.patch('core.ycheck.scenarios.issue_utils.add_issue')
    def test_unattended_upgrades(self, mock_add_issue):
        issues = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('Unattended upgrades are enabled which can lead to '
               'uncontrolled changes to this environment. If maintenance '
               'windows are required please consider disabling unattended '
               'upgrades.')
        self.assertEqual(issues[SystemWarning], [msg])
