from datetime import datetime, timezone
from util.db_utils import DynamoDB, DynamoDBError
from model.product_data import Product
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from util.secrets_utils import get_secret
import boto3
import os

class ProductModel:
   
    # Initialize OpenSearch client
    def  get_opensearch_client():
        # Get OpenSearch configuration from Secrets Manager
        try:
            secrets = get_secret('opensearch/config')
            host = secrets.get('host')
            region = secrets.get('region')
            master_user_name = secrets.get('master_user_name')
            master_user_password = secrets.get('master_user_password')


            return OpenSearch(
                hosts=[{'host': host, 'port': 443}],
                http_auth=(master_user_name, master_user_password),  # Replace with your master user credentials
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
                timeout=30,  # Increase timeout to 30 seconds
                retry_on_timeout=True,
                max_retries=3
            )
        except Exception as e:
            print(f"Error initializing OpenSearch client: {str(e)}")
            raise e


    def create_index_mapping():
        mapping = {
            "mappings": {
                "properties": {
                    "product_id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "analyzer": "custom_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "completion": {"type": "completion"},
                            "fuzzy": {
                                "type": "text",
                                "analyzer": "custom_fuzzy_analyzer"
                            }
                        }
                    },
                    "brand_name": {
                        "type": "text",
                        "analyzer": "custom_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "fuzzy": {
                                "type": "text",
                                "analyzer": "custom_fuzzy_analyzer"
                            }
                        }
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "custom_analyzer",
                        "fields": {
                            "fuzzy": {
                                "type": "text",
                                "analyzer": "custom_fuzzy_analyzer"
                            }
                        }
                    },
                    "tags": {
                        "type": "text",
                        "analyzer": "custom_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "fuzzy": {
                                "type": "text",
                                "analyzer": "custom_fuzzy_analyzer"
                            }
                        }
                    },
                    # Other fields remain the same
                    "category_id": {"type": "keyword"},
                    "price": {
                        "type": "float",
                        "fields": {
                            "raw": {"type": "keyword"}
                        }
                    },
                    "sku": {"type": "keyword"},
                    "stock": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "specifications": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "keyword"},
                            "value": {
                                "type": "text",
                                "fields": {
                                    "keyword": {"type": "keyword"},
                                    "fuzzy": {
                                        "type": "text",
                                        "analyzer": "custom_fuzzy_analyzer"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "settings": {
                "analysis": {
                    "analyzer": {
                        "custom_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "word_delimiter",
                                "custom_edge_ngram"
                            ]
                        },
                        "custom_fuzzy_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "custom_shingle",
                                "custom_edge_ngram"
                            ]
                        }
                    },
                    "filter": {
                        "custom_edge_ngram": {
                            "type": "edge_ngram",
                            "min_gram": 2,
                            "max_gram": 15
                        },
                        "custom_shingle": {
                            "type": "shingle",
                            "min_shingle_size": 2,
                            "max_shingle_size": 3,
                            "output_unigrams": True
                        }
                    }
                }
            }
        }
        return mapping
    

            
    @staticmethod
    def index_product(product):
        # Prepare document with enhanced data
        document = {
            'product_id': product['product_id'],
            'name': product['name'],
            'brand_name': product['brand_name'],
            'category_id': product['category_id'],
            'description': product['description'],
            'product_image_url': product['product_image_url'],
            'price': float(product['price']),
            'tags': product.get('tags', []),
            'specifications': product.get('specifications', []),
            'variants': product.get('variants', []),
            'stock': product.get('stock', 0),
            'created_at': product.get('created_at', datetime.now().isoformat()),
            'updated_at': datetime.now().isoformat()
        }
        
        try:
            opensearch_client = ProductModel.get_opensearch_client()
            print("OpenSearch Client Configuration:", opensearch_client.transport.hosts)
            

            # Create index with mapping if it doesn't exist
            if not opensearch_client.indices.exists(index='products'):
                opensearch_client.indices.create(
                    index='products',
                    body=ProductModel.create_index_mapping()
                )

            # Index the document
            print("Indexing document:", document)
            response = opensearch_client.index(
                index='products',
                body=document,
                id=str(product['product_id']),
                refresh=True
            )

            # # Verify the document was indexed
            # verify = opensearch_client.get(
            #     index='products',
            #     id=str(product['product_id'])
            # )
            # print("Verification response:", verify)

            print('indexed the product successfully')
            return response
        
        except Exception as e:
            print(f"Error indexing product: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Full error details: {e.__dict__}")
            raise e
        
    

    @staticmethod
    def create_product(product_data):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        current_time = datetime.now(timezone.utc).isoformat()
        product_data['product_id'] = product_data.get('product_id', os.urandom(8).hex())
        product_data['created_at'] = current_time
        product_data['updated_at'] = current_time

        
        product = Product.from_dict(product_data)
        
        try:
            table.put_item(Item=product.to_dict())
            return product
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error creating and inserting the product: {str(e)}")

    @staticmethod
    def get_all_products(category_id=None):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        print(category_id)
        try:
            if category_id:
                response = table.scan(
                    FilterExpression='category_id = :category_id',
                    ExpressionAttributeValues={':category_id': category_id}
                )
            else:
                response = table.scan()

            items = response.get('Items', [])
            
            while 'LastEvaluatedKey' in response:
                response = table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response['Items'])
            
            return items
            # return [Product.from_dict(item) for item in items]
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error fetching products from the db: {str(e)}")

    @staticmethod        
    def get_product(product_id):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        try:
            response = table.get_item(Key={'product_id': product_id})
            item = response.get('Item')
            return item
        
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error fetching products from the db for id {product_id}: {str(e)}")

    @staticmethod
    def delete_product(product_id):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        try:
            response = table.delete_item(Key={'product_id': product_id}, ReturnValues="ALL_OLD")
            print(response)
            if 'Attributes' in response:
                return 'Product deleted successfully'
            return 404
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error deleting products from the db for id {product_id}: {str(e)}")

    @staticmethod        
    def update_product(product_id, updated_data):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            updated_data['updated_at'] = current_time
            product = Product.from_dict(updated_data)

            response = table.update_item(
                Key={'product_id': product_id},
                UpdateExpression="SET  price = :price, stock = :stock, updated_at = :updated_at, description = :description",
                ExpressionAttributeValues={
                    ':price': product.price,    
                    ':stock': product.stock,
                    ':updated_at': product.updated_at,
                    ':description': product.description
                },
                ReturnValues="ALL_NEW"
            )

            if 'Attributes' in response:
                return response['Attributes']
            return None
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error updating products from the db for id {product_id}: {str(e)}")

    @staticmethod
    def update_stock(product_id, updated_stock):
        table_name = 'Products'
        con = DynamoDB.get_connection()
        table = con.Table(table_name)
        try:
            response = table.update_item(
                Key={'product_id': product_id},
                UpdateExpression="SET stock = :stock",
                ExpressionAttributeValues={':stock': updated_stock},
                ReturnValues="ALL_NEW"
            )

            if 'Attributes' in response:
                return Product.from_dict(response['Attributes'])
            return None
        except DynamoDBError as e:
            # amazonq-ignore-next-line
            raise Exception(f"Error updating stock for product {product_id}: {str(e)}")

