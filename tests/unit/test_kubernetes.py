import os

import mock

from tests.unit import utils

from core.issues.issue_types import KubernetesWarning
from core import checks, cli_helpers
from core.plugins import kubernetes as kubernetes_core
from core.ycheck.bugs import YBugChecker
from core.ycheck.scenarios import YScenarioChecker
from plugins.kubernetes.pyparts import (
    service_info,
    network_checks,
)


class KubernetesTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'kubernetes'
        os.environ["DATA_ROOT"] = \
            os.path.join(utils.TESTS_DIR, 'fake_data_root/kubernetes')


class TestKubernetesServiceInfo(KubernetesTestsBase):

    def setUp(self):
        self.snaps_list = cli_helpers.CLIHelper().snap_list_all()
        super().setUp()

    def test_get_service_info(self):
        expected = {'systemd': {
                        'enabled': [
                            'calico-node',
                            'containerd',
                            'flannel',
                            'kube-proxy-iptables-fix',
                            'snap.kube-apiserver.daemon',
                            'snap.kube-controller-manager.daemon',
                            'snap.kube-proxy.daemon',
                            'snap.kube-scheduler.daemon']
                        },
                    'ps': [
                        'calico-node (3)',
                        'containerd (1)',
                        'containerd-shim-runc-v2 (1)',
                        'flanneld (1)',
                        'kube-apiserver (1)',
                        'kube-controller-manager (1)',
                        'kube-proxy (1)',
                        'kube-scheduler (1)']}
        inst = service_info.KubernetesServiceChecks()
        inst()
        self.assertEqual(inst.output['services'], expected)

    def test_get_snap_info_from_line(self):
        result = ['cdk-addons 1.23.0',
                  'core 16-2.54.2',
                  'core18 20211215',
                  'core20 20220114',
                  'kube-apiserver 1.23.3',
                  'kube-controller-manager 1.23.3',
                  'kube-proxy 1.23.3',
                  'kube-scheduler 1.23.3',
                  'kubectl 1.23.3']
        inst = service_info.KubernetesPackageChecks()
        inst()
        self.assertEqual(inst.output['snaps'], result)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_snap_info_from_line_no_k8s(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for pkg in kubernetes_core.K8S_PACKAGES:
                obj = service_info.KubernetesPackageChecks()
                if obj.snap_check._get_snap_info_from_line(line, pkg):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_helper.return_value.snap_list_all.return_value = filterered_snaps
        inst = service_info.KubernetesPackageChecks()
        inst()
        self.assertFalse(inst.plugin_runnable)
        self.assertEqual(inst.output, None)


class TestKubernetesNetworkChecks(KubernetesTestsBase):

    def test_get_network_info(self):
        expected = {'flannel':
                    {'flannel.1': {'addr': '10.1.84.0',
                                   'vxlan': {'dev': 'ens3',
                                             'id': '1',
                                             'local_ip': '10.6.3.201'}}}}
        inst = network_checks.KubernetesNetworkChecks()
        inst()
        self.assertEqual(inst.output, expected)


class TestKubernetesBugChecks(KubernetesTestsBase):

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


class TestKubernetesScenarioChecks(KubernetesTestsBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('system_cpufreq_mode.yaml'))
    @mock.patch('core.plugins.system.SystemBase.virtualisation_type',
                None)
    @mock.patch('core.plugins.kernel.CPU.cpufreq_scaling_governor_all',
                'powersave')
    @mock.patch('core.plugins.kubernetes.KubernetesChecksBase.plugin_runnable',
                True)
    @mock.patch.object(checks, 'CLIHelper')
    @mock.patch('core.ycheck.scenarios.issue_utils.add_issue')
    def test_system_cpufreq_mode(self, mock_add_issue, mock_cli):
        issues = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.snap_list_all.return_value = \
            ['kubelet 1.2.3 123\n']

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('This node is used for Kubernetes but is not using '
               'cpufreq scaling_governor in "performance" mode '
               '(actual=powersave). This is not recommended and can result in '
               'performance degradation. To fix this you can install '
               'cpufrequtils and set "GOVERNOR=performance" in '
               '/etc/default/cpufrequtils. NOTE: requires node reboot to '
               'take effect.')
        self.assertEqual(issues[KubernetesWarning], [msg])
