"""Offline tests for deployment safeguards; no hosting account is contacted."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_pythonanywhere as deploy
import package_hosting
import run_pythonanywhere as launcher
import smoke_hosted


class HostingTests(unittest.TestCase):
    def test_no_token_in_new_console_fails_with_safe_instructions(self):
        with self.assertRaisesRegex(RuntimeError, 'NEW Bash console'):
            deploy.hosting_identity({}, 'tester')

    def test_us_account(self):
        self.assertEqual(deploy.hosting_identity({'API_TOKEN': 'test'}, 'tester'),
                         ('www.pythonanywhere.com', 'tester', 'tester.pythonanywhere.com', 'test'))

    def test_eu_account(self):
        self.assertEqual(deploy.hosting_identity({'API_TOKEN': 'test', 'PYTHONANYWHERE_SITE': 'eu.pythonanywhere.com'}, 'tester')[2],
                         'tester.eu.pythonanywhere.com')

    def test_account_host_must_be_pythonanywhere(self):
        with self.assertRaises(RuntimeError):
            deploy.hosting_identity({'API_TOKEN': 'test', 'PYTHONANYWHERE_SITE': 'other.example'}, 'tester')

    def test_account_token_never_sent_to_github(self):
        with self.assertRaisesRegex(ValueError, 'another service'):
            deploy.request_json('https://api.github.com/x', token='test')

    def test_https_api_only(self):
        with self.assertRaises(ValueError):
            deploy.request_json('http://www.pythonanywhere.com/x', token='test')

    def test_launcher_keeps_data_outside_release(self):
        env, command = launcher.runtime_config(Path('/home/me/site'), Path('/home/me'),
                                               'me.pythonanywhere.com', '/var/sockets/me/app.sock')
        self.assertEqual(env['DATA_DIR'], '/home/me/signal-clone-data')
        self.assertEqual(env['SQLITE_JOURNAL_MODE'], 'DELETE')
        self.assertEqual(env['COOKIE_SECURE'], 'true')
        self.assertEqual(env['ALLOWED_ORIGINS'], 'https://me.pythonanywhere.com')
        self.assertEqual(command[command.index('--workers') + 1], '1')
        self.assertEqual(command[command.index('--uds') + 1], '/var/sockets/me/app.sock')

    def test_launcher_rejects_invalid_domain(self):
        with self.assertRaises(ValueError):
            launcher.runtime_config(Path('/app'), Path('/home/u'), 'evil.example', '/socket')

    def test_launcher_requires_managed_socket(self):
        with self.assertRaises(ValueError):
            launcher.runtime_config(Path('/app'), Path('/home/u'), 'u.pythonanywhere.com', '')

    def _archive(self, path, extra=None, missing=False):
        with zipfile.ZipFile(path, 'w') as z:
            for name in ['backend/app/main.py', 'frontend/out/index.html', 'scripts/run_pythonanywhere.py']:
                if not (missing and 'index.html' in name):
                    z.writestr('signal-clone/' + name, 'placeholder')
            z.writestr('signal-clone/build-manifest.json', json.dumps({'commit': 'abc', 'repository': 'owner/repo'}))
            if extra:
                z.writestr(*extra)

    def test_valid_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.zip'
            self._archive(path)
            self.assertEqual(deploy.validate_archive(path)['commit'], 'abc')

    def test_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.zip'
            self._archive(path, ('signal-clone/../../escape', 'bad'))
            with self.assertRaisesRegex(ValueError, 'unsafe path'):
                deploy.validate_archive(path)

    def test_archive_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.zip'
            link = zipfile.ZipInfo('signal-clone/link')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            self._archive(path, (link, '/etc/passwd'))
            with self.assertRaisesRegex(ValueError, 'symbolic link'):
                deploy.validate_archive(path)

    def test_archive_requires_built_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.zip'
            self._archive(path, missing=True)
            with self.assertRaisesRegex(ValueError, 'missing'):
                deploy.validate_archive(path)

    def test_release_uses_current_commit_not_latest(self):
        responses = [{'default_branch': 'main'}, {'sha': '123abc'}, {'assets': [
            {'name': 'signal-hosting.zip', 'browser_download_url': 'https://github.com/owner/repo/z'},
            {'name': 'signal-hosting.sha256', 'browser_download_url': 'https://github.com/owner/repo/s'},
        ]}]
        with patch.object(deploy, 'request_json', side_effect=responses) as request:
            sha, assets = deploy.wait_for_release('owner/repo', attempts=1)
        self.assertEqual(sha, '123abc')
        self.assertIn('/releases/tags/deploy-123abc', request.call_args.args[0])
        self.assertEqual(len(assets), 2)

    def test_missing_release_stops_instead_of_deploying_an_older_one(self):
        error = HTTPError('https://api.github.com/x', 404, 'not found', None, None)
        with patch.object(deploy, 'request_json', side_effect=[{'default_branch': 'main'}, {'sha': 'abc'}, error]), patch.object(deploy.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'workflow'):
                deploy.wait_for_release('owner/repo', attempts=1)

    def test_unrelated_existing_site_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'argv', ['deploy', '--repo', 'owner/repo']), \
                 patch.object(deploy, 'hosting_identity', return_value=('www.pythonanywhere.com', 'tester', 'tester.pythonanywhere.com', 'test')), \
                 patch.object(deploy.Path, 'home', return_value=Path(directory)), \
                 patch.object(deploy, 'request_json', return_value={'webapp': {'command': 'some-other-app'}}) as request:
                with self.assertRaisesRegex(RuntimeError, 'different app'):
                    deploy.main()
                self.assertEqual(request.call_count, 1)
                self.assertFalse((Path(directory) / 'signal-clone-runtime').exists())

    def test_package_requires_frontend_build(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                package_hosting.package(Path(directory))

    def test_public_check_requires_https(self):
        with self.assertRaises(ValueError):
            smoke_hosted.validate_origin('http://demo.example')
        self.assertEqual(smoke_hosted.validate_origin('http://127.0.0.1:8000', True), 'http://127.0.0.1:8000')

    def test_origin_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            smoke_hosted.validate_origin('https://user:pass@demo.example')


if __name__ == '__main__':
    unittest.main()
