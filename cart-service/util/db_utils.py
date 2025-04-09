import boto3
import json
import requests
from botocore.exceptions import ClientError
from util.secrets_utils import get_secret
from util.circuit_breaker import circuit_breaker
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DynamoDBError(Exception):
    """Custom exception for Secrets Manager errors"""
    pass

class DynamoDBConn:

    @classmethod
    @circuit_breaker('dynamodb-orders-connection', failure_threshold=5, reset_timeout=60,fallback_function=lambda: None)
    def get_connection(self):
        if os.environ.get('dynamo_db_secret') is None:
            os.environ['dynamo_db_secret'] = json.dumps(get_secret(f"dev/dynamodb/config")  )

        secret = json.loads(os.environ.get('dynamo_db_secret'))
        print(secret)

        return boto3.resource('dynamodb',
            region_name=secret['region'],
            aws_access_key_id=secret['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=secret['AWS_SECRET_ACCESS_KEY']
        )
    
def get_product_details(product_id):
    # Assuming product service URL is stored in environment variable
    logger.info('calling',f"http://product-service-ecs-connect:5002/products/{product_id}")
    product_service_url = f"http://product-service-ecs-connect:5002/products/{product_id}"
    response = requests.get(product_service_url)
    logger.info('product response', response)
    
    print(response.json())
    if response.status_code == 200:
        return response.json()
    return None
    

def table_exists(con, table_name):
    try:
        table = con.Table(table_name)
        table.load()
        print(f"Table {table_name} exists")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Table {table_name} does not exist")
            return False
        raise
     
def init_dynamodb():
    table_name = 'Cart'

    con = DynamoDBConn.get_connection()

    if not table_exists(con, table_name):
        try:
            # Create the DynamoDB table
            table = con.create_table(
                                        TableName='Cart',
                                        KeySchema=[
                                            {
                                                'AttributeName': 'cart_id',
                                                'KeyType': 'HASH'  # Partition key
                                            },
                                            {
                                                'AttributeName': 'user_id',
                                                'KeyType': 'RANGE'  # Sort key
                                            }
                                        ],
                                        AttributeDefinitions=[
                                            {
                                                'AttributeName': 'cart_id',
                                                'AttributeType': 'S'
                                            },
                                            {
                                                'AttributeName': 'user_id',
                                                'AttributeType': 'S'
                                            }
                                        ],
                                        GlobalSecondaryIndexes=[
                                            {
                                                'IndexName': 'UserIdIndex',
                                                'KeySchema': [
                                                    {
                                                        'AttributeName': 'user_id',
                                                        'KeyType': 'HASH'
                                                    }
                                                ],
                                                'Projection': {
                                                    'ProjectionType': 'ALL'
                                                },
                                                'ProvisionedThroughput': {
                                                    'ReadCapacityUnits': 5,
                                                    'WriteCapacityUnits': 5
                                                }
                                            }
                                        ],
                                        ProvisionedThroughput={
                                            'ReadCapacityUnits': 5,
                                            'WriteCapacityUnits': 5
                                        }
                                    )

            print(f"Creating table {table_name}...")
            
            # Wait for the table to be created
            table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
            print(f"Table {table_name} created successfully!")
        except ClientError as e:
            print(f"Error creating table: {e}")
            raise
    else:
        return con.Table(table_name)
    


