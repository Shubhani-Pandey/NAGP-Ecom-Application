# utils/cognito_utils.py
import boto3
from utils.secrets_utils import get_secret
import requests
import json
import os
from jwt.algorithms import RSAAlgorithm
from utils.circuit_breaker import circuit_breaker

class CognitoError(Exception):
    """Custom exception for Cognito operations"""
    pass

class CognitoClient:
    _instance = None
    _cognito_config = None
    _jwt_keys = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CognitoClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        try:

            if os.environ.get('cognito_secret')=='':
                os.environ['cognito_secret'] = get_secret('dev/cognito/config')     
                
            self._cognito_config = json.loads(os.environ.get('cognito_secret'))
            self.client = boto3.client('cognito-idp')
        except Exception as e:
            raise CognitoError(f"Cognito initialization error: {str(e)}")

    def get_config(self):
        return self._cognito_config

    def get_public_keys(self):
        """Fetch public keys from Cognito"""
        if not self._jwt_keys:
            region = self._cognito_config['region']
            pool_id = self._cognito_config['user_pool_id']
            url = f'https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json'
            response = requests.get(url)
            keys = response.json()['keys']
            for key in keys:
                kid = key['kid']
                self._jwt_keys[kid] = RSAAlgorithm.from_jwk(json.dumps(key))
        return self._jwt_keys

    @circuit_breaker('cognito-register',failure_threshold=3, reset_timeout=30)
    def register_user(self, username, password, email, phoneNumber, gender, address, birthdate,name):
        try:
            response = self.client.sign_up(
                ClientId=self._cognito_config['client_id'],
                Username=username,
                Password=password,
                UserAttributes=[
                    {
                        'Name': 'email',
                        'Value': email
                    },
                    # {
                    #     'Name': 'phone_number',
                    #     'Value': phoneNumber
                    # },
                    # {
                    #     'Name': 'gender',
                    #     'Value': gender
                    # },
                    # {
                    #     'Name': 'address',
                    #     'Value': address
                    # },
                    # {
                    #     'Name': 'birthdate',
                    #     'Value': birthdate
                    # },
                    # {
                    #     'Name': 'name',
                    #     'Value': name
                    # }
                ]
            )
            return response
        except Exception as e:
            raise CognitoError(f"User registration error: {str(e)}")

    def confirm_registration(self, username, confirmation_code):
        try:
            return self.client.confirm_sign_up(
                ClientId=self._cognito_config['client_id'],
                Username=username,
                ConfirmationCode=confirmation_code
            )
        except Exception as e:
            raise CognitoError(f"Registration confirmation error: {str(e)}")

    @circuit_breaker('cognito-login', failure_threshold=3, reset_timeout=30)
    def login(self, username, password):
        try:
            response = self.client.initiate_auth(
                ClientId=self._cognito_config['client_id'],
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            return response['AuthenticationResult']
        except Exception as e:
            raise CognitoError(f"Login error: {str(e)}")
       
    def logout(self, access_token):
        try:
            return self.client.global_sign_out(AccessToken=access_token)
        except Exception as e:
            raise CognitoError(f"Logout error: {str(e)}")
