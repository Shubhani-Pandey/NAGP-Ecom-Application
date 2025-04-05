# utils/secrets_utils.py
import boto3
import json
import os

class SecretsManagerError(Exception):
    """Custom exception for Secrets Manager errors"""
    pass

def get_secret(secret_name):
    """Retrieve a secret from AWS Secrets Manager"""
    session = boto3.session.Session()
    client = session.client('secretsmanager')

    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        raise SecretsManagerError(f"Failed to retrieve secret: {str(e)}")
    

def load_secrets():
    secrets = get_secret(os.environ.get('SECRETS_ARN'))
    
    # Set environment variables from secrets
    os.environ['OPENSEARCH_HOST'] = secrets['OPENSEARCH_HOST']
    os.environ['OPENSEARCH_PORT'] = secrets['OPENSEARCH_PORT']
    os.environ['OPENSEARCH_USER'] = secrets['OPENSEARCH_USER']
    os.environ['OPENSEARCH_PASSWORD'] = secrets['OPENSEARCH_PASSWORD']