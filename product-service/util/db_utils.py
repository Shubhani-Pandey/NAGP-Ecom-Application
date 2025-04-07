import boto3
import json
import os
from botocore.exceptions import ClientError
from util.secrets_utils import get_secret
from util.circuit_breaker import circuit_breaker

class DynamoDBError(Exception):
    """Custom exception for Secrets Manager errors"""
    pass

class DynamoDB:

    @classmethod
    @circuit_breaker('dynamodb-products-connection', failure_threshold=5, reset_timeout=60,fallback_function=lambda: None)
    def get_connection(self):
        if os.environ.get('dynamo_db_secret')=='':
            os.environ['dynamo_db_secret'] = get_secret(f"dev/dynamodb/config") 

        secret = json.loads(os.environ.get('dynamo_db_secret'))
        print(secret)

        return boto3.resource('dynamodb',
            region_name=secret['region'],
            aws_access_key_id=secret['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=secret['AWS_SECRET_ACCESS_KEY']
        )
    

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
    table_name = 'Products'

    con = DynamoDB.get_connection()

    if not table_exists(con, table_name):
        try:
            # Create the DynamoDB table
            table = con.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': 'product_id',
                        'KeyType': 'HASH'  # Partition key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'product_id',
                        'AttributeType': 'S'  # String
                    },
                    {
                        'AttributeName': 'category_id',
                        'AttributeType': 'S'  # String
                    }
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'CategoryIndex',
                        'KeySchema': [
                            {
                                'AttributeName': 'category_id',
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
