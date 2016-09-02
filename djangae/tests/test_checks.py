import os
import tempfile

import yaml
from mock import patch

from djangae.checks import check_deferred_builtin
from djangae.environment import get_application_root
from djangae.test import TestCase


class ChecksTestCase(TestCase):
    def test_deferred_builtin_on(self):
        # Read and parse app.yaml
        app_yaml_path = os.path.join(get_application_root(), "app.yaml")
        with open(app_yaml_path, 'r') as f:
            app_yaml = yaml.load(f.read())
        builtins = app_yaml.get('builtins', [])

        # Switch on deferred builtin
        builtins.append({'deferred': 'on'})
        app_yaml['builtins'] = builtins

        # Write to temporary app.yaml
        temp_app_yaml_dir = tempfile.mkdtemp()
        temp_app_yaml_path = os.path.join(temp_app_yaml_dir, "app.yaml")
        temp_app_yaml = file(temp_app_yaml_path, 'w')
        yaml.dump(app_yaml, temp_app_yaml)

        with patch('djangae.checks.get_application_root') as mock_app_root:
            mock_app_root.return_value = temp_app_yaml_dir

            warnings = check_deferred_builtin()
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].id, 'djangae.W001')

    def test_deferred_builtin_off(self):
        warnings = check_deferred_builtin()
        self.assertEqual(len(warnings), 0)

