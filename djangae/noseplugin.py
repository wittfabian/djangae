from django.conf import settings
from djangae.utils import find_project_root

from google.appengine.ext import testbed
from google.appengine.datastore import datastore_stub_util
from nose.plugins import Plugin


class DjangaePlugin(Plugin):
    enabled = True
    def configure(self, options, conf):
        pass

    def startTest(self, test):
        use_scattered = not getattr(settings, "DJANGAE_SEQUENTIAL_IDS_IN_TESTS", False)

        stub_kwargs = {
            "init_datastore_v3_stub": {
                "use_sqlite": True,
                "auto_id_policy": testbed.AUTO_ID_POLICY_SCATTERED if use_scattered else testbed.AUTO_ID_POLICY_SEQUENTIAL,
                "consistency_policy": datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=1)
            },
            "init_taskqueue_stub": {
                "root_path": find_project_root()
            }
        }

        self.bed = testbed.Testbed()
        self.bed.activate()
        for init_name in testbed.INIT_STUB_METHOD_NAMES.values():
            getattr(self.bed, init_name)(**stub_kwargs.get(init_name, {}))

    def stopTest(self, test):
        self.bed.deactivate()
