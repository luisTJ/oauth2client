# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Oauth2client tests.

Unit tests for service account credentials implemented using RSA.
"""

import datetime
import json
import os
import rsa
import tempfile

import mock
import unittest2

from .http_mock import HttpMockSequence
from oauth2client import crypt
from oauth2client.service_account import ServiceAccountCredentials
from oauth2client.service_account import SERVICE_ACCOUNT


def data_filename(filename):
    return os.path.join(os.path.dirname(__file__), 'data', filename)


def datafile(filename):
    with open(data_filename(filename), 'rb') as file_obj:
        return file_obj.read()


class ServiceAccountCredentialsTests(unittest2.TestCase):

    def setUp(self):
        self.client_id = '123'
        self.service_account_email = 'dummy@google.com'
        self.private_key_id = 'ABCDEF'
        self.private_key = datafile('pem_from_pkcs12.pem')
        self.scopes = ['dummy_scope']
        self.signer = crypt.Signer.from_string(self.private_key)
        self.credentials = ServiceAccountCredentials(
            self.service_account_email,
            self.signer,
            private_key_id=self.private_key_id,
            client_id=self.client_id,
        )

    def test__to_json_override(self):
        signer = object()
        creds = ServiceAccountCredentials('name@email.com',
                                          signer)
        self.assertEqual(creds._signer, signer)
        # Serialize over-ridden data (unrelated to ``creds``).
        to_serialize = {'unrelated': 'data'}
        serialized_str = creds._to_json([], to_serialize.copy())
        serialized_data = json.loads(serialized_str)
        expected_serialized = {
            '_class': 'ServiceAccountCredentials',
            '_module': 'oauth2client.service_account',
            'token_expiry': None,
        }
        expected_serialized.update(to_serialize)
        self.assertEqual(serialized_data, expected_serialized)

    def test_sign_blob(self):
        private_key_id, signature = self.credentials.sign_blob('Google')
        self.assertEqual(self.private_key_id, private_key_id)

        pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(
            datafile('publickey_openssl.pem'))

        self.assertTrue(rsa.pkcs1.verify(b'Google', signature, pub_key))

        self.assertRaises(rsa.pkcs1.VerificationError,
                          rsa.pkcs1.verify, b'Orest', signature, pub_key)
        self.assertRaises(rsa.pkcs1.VerificationError,
                          rsa.pkcs1.verify,
                          b'Google', b'bad signature', pub_key)

    def test_service_account_email(self):
        self.assertEqual(self.service_account_email,
                         self.credentials.service_account_email)

    @staticmethod
    def _from_json_keyfile_name_helper(payload, scopes=None):
        filehandle, filename = tempfile.mkstemp()
        os.close(filehandle)
        try:
            with open(filename, 'w') as file_obj:
                json.dump(payload, file_obj)
            return ServiceAccountCredentials.from_json_keyfile_name(
                filename, scopes=scopes)
        finally:
            os.remove(filename)

    @mock.patch('oauth2client.crypt.Signer.from_string',
                return_value=object())
    def test_from_json_keyfile_name_factory(self, signer_factory):
        client_id = 'id123'
        client_email= 'foo@bar.com'
        private_key_id = 'pkid456'
        private_key = 's3kr3tz'
        payload = {
            'type': SERVICE_ACCOUNT,
            'client_id': client_id,
            'client_email': client_email,
            'private_key_id': private_key_id,
            'private_key': private_key,
        }
        scopes = ['foo', 'bar']
        creds = self._from_json_keyfile_name_helper(payload, scopes=scopes)
        self.assertIsInstance(creds, ServiceAccountCredentials)
        self.assertEqual(creds.client_id, client_id)
        self.assertEqual(creds._service_account_email, client_email)
        self.assertEqual(creds._private_key_id, private_key_id)
        self.assertEqual(creds._private_key_pkcs8_pem, private_key)
        self.assertEqual(creds._scopes, ' '.join(scopes))
        # Check stub.
        self.assertEqual(creds._signer, signer_factory.return_value)
        signer_factory.assert_called_once_with(private_key)

    def test_from_json_keyfile_name_factory_bad_type(self):
        type_ = 'bad-type'
        self.assertNotEqual(type_, SERVICE_ACCOUNT)
        payload = {'type': type_}
        with self.assertRaises(ValueError):
            self._from_json_keyfile_name_helper(payload)

    def test_from_json_keyfile_name_factory_missing_field(self):
        payload = {
            'type': SERVICE_ACCOUNT,
            'client_id': 'my-client',
        }
        with self.assertRaises(KeyError):
            self._from_json_keyfile_name_helper(payload)

    def _from_p12_keyfile_helper(self, private_key_password=None, scopes=''):
        service_account_email = 'name@email.com'
        filename = data_filename('privatekey.p12')
        with open(filename, 'rb') as file_obj:
            key_contents = file_obj.read()
        creds = ServiceAccountCredentials.from_p12_keyfile(
            service_account_email, filename,
            private_key_password=private_key_password,
            scopes=scopes)
        self.assertIsInstance(creds, ServiceAccountCredentials)
        self.assertIsNone(creds.client_id)
        self.assertEqual(creds._service_account_email, service_account_email)
        self.assertIsNone(creds._private_key_id)
        self.assertIsNone(creds._private_key_pkcs8_pem)
        self.assertEqual(creds._private_key_pkcs12, key_contents)
        if private_key_password is not None:
            self.assertEqual(creds._private_key_password, private_key_password)
        self.assertEqual(creds._scopes, ' '.join(scopes))

    def _p12_not_implemented_helper(self):
        service_account_email = 'name@email.com'
        filename = data_filename('privatekey.p12')
        with self.assertRaises(NotImplementedError):
            ServiceAccountCredentials.from_p12_keyfile(
                service_account_email, filename)

    @mock.patch('oauth2client.crypt.Signer', new=crypt.PyCryptoSigner)
    def test_from_p12_keyfile_with_pycrypto(self):
        self._p12_not_implemented_helper()

    @mock.patch('oauth2client.crypt.Signer', new=crypt.RsaSigner)
    def test_from_p12_keyfile_with_rsa(self):
        self._p12_not_implemented_helper()

    def test_from_p12_keyfile_defaults(self):
        self._from_p12_keyfile_helper()

    def test_from_p12_keyfile_explicit(self):
        password = 'notasecret'
        self._from_p12_keyfile_helper(private_key_password=password,
                                      scopes=['foo', 'bar'])

    def test_from_p12_keyfile_buffer(self):
        service_account_email = 'name@email.com'
        filename = data_filename('privatekey.p12')
        private_key_password = 'notasecret'
        scopes = ['foo', 'bar']
        with open(filename, 'rb') as file_obj:
            key_contents = file_obj.read()
            # Seek back to the beginning so the buffer can be
            # passed to the constructor.
            file_obj.seek(0)
            creds = ServiceAccountCredentials.from_p12_keyfile_buffer(
                service_account_email, file_obj,
                private_key_password=private_key_password,
                scopes=scopes)
        # Check the created object.
        self.assertIsInstance(creds, ServiceAccountCredentials)
        self.assertIsNone(creds.client_id)
        self.assertEqual(creds._service_account_email, service_account_email)
        self.assertIsNone(creds._private_key_id)
        self.assertIsNone(creds._private_key_pkcs8_pem)
        self.assertEqual(creds._private_key_pkcs12, key_contents)
        self.assertEqual(creds._private_key_password, private_key_password)
        self.assertEqual(creds._scopes, ' '.join(scopes))

    def test_create_scoped_required_without_scopes(self):
        self.assertTrue(self.credentials.create_scoped_required())

    def test_create_scoped_required_with_scopes(self):
        signer = object()
        self.credentials = ServiceAccountCredentials(
            self.service_account_email,
            signer,
            scopes=self.scopes,
            private_key_id=self.private_key_id,
            client_id=self.client_id,
        )
        self.assertFalse(self.credentials.create_scoped_required())

    def test_create_scoped(self):
        new_credentials = self.credentials.create_scoped(self.scopes)
        self.assertNotEqual(self.credentials, new_credentials)
        self.assertIsInstance(new_credentials,
                              ServiceAccountCredentials)
        self.assertEqual('dummy_scope', new_credentials._scopes)

    def test_create_delegated(self):
        signer = object()
        sub = 'foo@email.com'
        creds = ServiceAccountCredentials('name@email.com', signer)
        self.assertNotIn('sub', creds._kwargs)
        delegated_creds = creds.create_delegated(sub)
        self.assertEqual(delegated_creds._kwargs['sub'], sub)
        # Make sure the original is unchanged.
        self.assertNotIn('sub', creds._kwargs)

    def test_create_delegated_existing_sub(self):
        signer = object()
        sub1 = 'existing@email.com'
        sub2 = 'new@email.com'
        creds = ServiceAccountCredentials('name@email.com', signer, sub=sub1)
        self.assertEqual(creds._kwargs['sub'], sub1)
        delegated_creds = creds.create_delegated(sub2)
        self.assertEqual(delegated_creds._kwargs['sub'], sub2)
        # Make sure the original is unchanged.
        self.assertEqual(creds._kwargs['sub'], sub1)

    @mock.patch('oauth2client.client._UTCNOW')
    def test_access_token(self, utcnow):
        # Configure the patch.
        seconds = 11
        NOW = datetime.datetime(1992, 12, 31, second=seconds)
        utcnow.return_value = NOW

        # Create a custom credentials with a mock signer.
        signer = mock.MagicMock()
        signed_value = b'signed-content'
        signer.sign = mock.MagicMock(name='sign',
                                     return_value=signed_value)
        credentials = ServiceAccountCredentials(
            self.service_account_email,
            signer,
            private_key_id=self.private_key_id,
            client_id=self.client_id,
        )

        # Begin testing.
        lifetime = 2  # number of seconds in which the token expires
        EXPIRY_TIME = datetime.datetime(1992, 12, 31,
                                        second=seconds + lifetime)

        token1 = u'first_token'
        token_response_first = {
            'access_token': token1,
            'expires_in': lifetime,
        }
        token2 = u'second_token'
        token_response_second = {
            'access_token': token2,
            'expires_in': lifetime,
        }
        http = HttpMockSequence([
            ({'status': '200'},
             json.dumps(token_response_first).encode('utf-8')),
            ({'status': '200'},
             json.dumps(token_response_second).encode('utf-8')),
        ])

        # Get Access Token, First attempt.
        self.assertIsNone(credentials.access_token)
        self.assertFalse(credentials.access_token_expired)
        self.assertIsNone(credentials.token_expiry)
        token = credentials.get_access_token(http=http)
        self.assertEqual(credentials.token_expiry, EXPIRY_TIME)
        self.assertEqual(token1, token.access_token)
        self.assertEqual(lifetime, token.expires_in)
        self.assertEqual(token_response_first,
                         credentials.token_response)
        # Two utcnow calls are expected:
        # - get_access_token() -> _do_refresh_request (setting expires in)
        # - get_access_token() -> _expires_in()
        expected_utcnow_calls = [mock.call()] * 2
        self.assertEqual(expected_utcnow_calls, utcnow.mock_calls)
        # One call to sign() expected: Actual refresh was needed.
        self.assertEqual(len(signer.sign.mock_calls), 1)

        # Get Access Token, Second Attempt (not expired)
        self.assertEqual(credentials.access_token, token1)
        self.assertFalse(credentials.access_token_expired)
        token = credentials.get_access_token(http=http)
        # Make sure no refresh occurred since the token was not expired.
        self.assertEqual(token1, token.access_token)
        self.assertEqual(lifetime, token.expires_in)
        self.assertEqual(token_response_first, credentials.token_response)
        # Three more utcnow calls are expected:
        # - access_token_expired
        # - get_access_token() -> access_token_expired
        # - get_access_token -> _expires_in
        expected_utcnow_calls = [mock.call()] * (2 + 3)
        self.assertEqual(expected_utcnow_calls, utcnow.mock_calls)
        # No call to sign() expected: the token was not expired.
        self.assertEqual(len(signer.sign.mock_calls), 1 + 0)

        # Get Access Token, Third Attempt (force expiration)
        self.assertEqual(credentials.access_token, token1)
        credentials.token_expiry = NOW  # Manually force expiry.
        self.assertTrue(credentials.access_token_expired)
        token = credentials.get_access_token(http=http)
        # Make sure refresh occurred since the token was not expired.
        self.assertEqual(token2, token.access_token)
        self.assertEqual(lifetime, token.expires_in)
        self.assertFalse(credentials.access_token_expired)
        self.assertEqual(token_response_second,
                         credentials.token_response)
        # Five more utcnow calls are expected:
        # - access_token_expired
        # - get_access_token -> access_token_expired
        # - get_access_token -> _do_refresh_request
        # - get_access_token -> _expires_in
        # - access_token_expired
        expected_utcnow_calls = [mock.call()] * (2 + 3 + 5)
        self.assertEqual(expected_utcnow_calls, utcnow.mock_calls)
        # One more call to sign() expected: Actual refresh was needed.
        self.assertEqual(len(signer.sign.mock_calls), 1 + 0 + 1)

        self.assertEqual(credentials.access_token, token2)
    
    def test_pass_in_optional_claim(self):

        scopes = []
        service_account_email = 'service@email.com'
        email = 'existing@email.com'

        key_location = data_filename('gcloud/application_default_credentials.json')
        credentials = ServiceAccountCredentials.from_json_keyfile_name(key_location, scopes=scopes, sub=email)
        self.assertEqual(credentials._kwargs['sub'], email)
        
        with open(data_filename('gcloud/application_default_credentials.json')) as file_obj:    
            data = json.load(file_obj)
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(data, scopes, sub=email)
        self.assertEqual(credentials._kwargs['sub'], email)

        key_location = data_filename('privatekey.p12')
        credentials = ServiceAccountCredentials.from_p12_keyfile(service_account_email, key_location, private_key_password=None, scope=scopes, sub=email)
        self.assertEqual(credentials._kwargs['sub'], email)

        with open(data_filename('privatekey.p12'), 'rb') as file_obj:
            credentials = ServiceAccountCredentials.from_p12_keyfile_buffer(service_account_email, file_obj, private_key_password=None, scope=scopes, sub=email)
            self.assertEqual(credentials._kwargs['sub'], email)


if __name__ == '__main__':  # pragma: NO COVER
    unittest2.main()
