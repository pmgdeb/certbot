"""Common utilities for certbot_nginx."""
import copy
import shutil
import tempfile
import unittest
import warnings

import josepy as jose
import mock
import pkg_resources
import zope.component

from certbot import configuration
from certbot.compat import os
from certbot.plugins import common
from certbot.tests import util as test_util

from certbot_nginx import configurator
from certbot_nginx import nginxparser


class NginxTest(unittest.TestCase):  # pylint: disable=too-few-public-methods

    def setUp(self):
        super(NginxTest, self).setUp()

        self.temp_dir, self.config_dir, self.work_dir = common.dir_setup(
            "etc_nginx", "certbot_nginx.tests")
        self.logs_dir = tempfile.mkdtemp('logs')

        self.config_path = os.path.join(self.temp_dir, "etc_nginx")

        self.rsa512jwk = jose.JWKRSA.load(test_util.load_vector(
            "rsa512_key.pem"))

    def tearDown(self):
        # On Windows we have various files which are not correctly closed at the time of tearDown.
        # For know, we log them until a proper file close handling is written.
        # Useful for development only, so no warning when we are on a CI process.
        def onerror_handler(_, path, excinfo):
            """On error handler"""
            if not os.environ.get('APPVEYOR'):  # pragma: no cover
                message = ('Following error occurred when deleting path {0}'
                           'during tearDown process: {1}'.format(path, str(excinfo)))
                warnings.warn(message)

        shutil.rmtree(self.temp_dir, onerror=onerror_handler)
        shutil.rmtree(self.config_dir, onerror=onerror_handler)
        shutil.rmtree(self.work_dir, onerror=onerror_handler)
        shutil.rmtree(self.logs_dir, onerror=onerror_handler)


def get_data_filename(filename):
    """Gets the filename of a test data file."""
    return pkg_resources.resource_filename(
        "certbot_nginx.tests", os.path.join(
            "testdata", "etc_nginx", filename))


def get_nginx_configurator(
        config_path, config_dir, work_dir, logs_dir, version=(1, 6, 2)):
    """Create an Nginx Configurator with the specified options."""

    backups = os.path.join(work_dir, "backups")

    with mock.patch("certbot_nginx.configurator.NginxConfigurator."
                    "config_test"):
        with mock.patch("certbot_nginx.configurator.util."
                        "exe_exists") as mock_exe_exists:
            mock_exe_exists.return_value = True
            config = configurator.NginxConfigurator(
                config=mock.MagicMock(
                    nginx_server_root=config_path,
                    le_vhost_ext="-le-ssl.conf",
                    config_dir=config_dir,
                    work_dir=work_dir,
                    logs_dir=logs_dir,
                    backup_dir=backups,
                    temp_checkpoint_dir=os.path.join(work_dir, "temp_checkpoints"),
                    in_progress_dir=os.path.join(backups, "IN_PROGRESS"),
                    server="https://acme-server.org:443/new",
                    http01_port=80,
                    https_port=5001,
                ),
                name="nginx",
                version=version)
            config.prepare()

    # Provide general config utility.
    nsconfig = configuration.NamespaceConfig(config.config)
    zope.component.provideUtility(nsconfig)

    return config


def filter_comments(tree):
    """Filter comment nodes from parsed configurations."""

    def traverse(tree):
        """Generator dropping comment nodes"""
        for entry in tree:
            # key, values = entry
            spaceless = [e for e in entry if not nginxparser.spacey(e)]
            if spaceless:
                key = spaceless[0]
                values = spaceless[1] if len(spaceless) > 1 else None
            else:
                key = values = ""
            if isinstance(key, list):
                new = copy.deepcopy(entry)
                new[1] = filter_comments(values)
                yield new
            else:
                if key != '#' and spaceless:
                    yield spaceless

    return list(traverse(tree))


def contains_at_depth(haystack, needle, n):
    """Is the needle in haystack at depth n?

    Return true if the needle is present in one of the sub-iterables in haystack
    at depth n. Haystack must be an iterable.
    """
    # Specifically use hasattr rather than isinstance(..., collections.Iterable)
    # because we want to include lists but reject strings.
    if not hasattr(haystack, '__iter__') or hasattr(haystack, 'strip'):
        return False
    if n == 0:
        return needle in haystack
    for item in haystack:
        if contains_at_depth(item, needle, n - 1):
            return True
    return False
