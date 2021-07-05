#!/usr/bin/python3
from openstack_common import OpenstackPackageChecksBase

YAML_PRIORITY = 3


class OpenstackPackageChecks(OpenstackPackageChecksBase):

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all