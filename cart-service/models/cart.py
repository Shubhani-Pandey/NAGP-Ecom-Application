from datetime import datetime, timezone
from decimal import Decimal
from util.db_utils import DynamoDBConn, get_product_details
from flask import Flask, request, jsonify
from .cart_data import Cart
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CartModel:

    @staticmethod
    def create_cart(user_id, cart_data):
        try:
            product_id = cart_data.get('product_id')
            quantity = cart_data.get('quantity', 1)
            current_time = datetime.now(timezone.utc).isoformat()

            logger.info(product_id, quantity, current_time)
            
            # Get product details from product service
            product = get_product_details(product_id)
            if product is None:
                jsonify({'error': 'Product not found'}), 404

            price = Decimal(str(product['price'])) * int(quantity)
            
            dynamodb = DynamoDBConn.get_connection()
            table = dynamodb.Table('Cart')

            # Generate deterministic cart_id for the user
            cart_id = f"cart_{user_id}"

            # First check if user already has a cart
            response = table.query(
                KeyConditionExpression='user_id = :user_id AND cart_id = :cart_id ',
                ExpressionAttributeValues={
                    ':user_id': user_id,
                    ':cart_id': cart_id
                }
            )

            if response['Items']:
                print('user already has a cart')
                # User has existing cart - update it
                existing_cart = response['Items'][0]
                cart_id = existing_cart['cart_id']

                print(existing_cart)
                
                # Check if product already exists in cart
                if product_id in existing_cart.get('products', {}):
                    print('found existing product with same id')
                    quantity = int(quantity)
                    # # Update quantity of existing product
                    # quantity = existing_cart['products'][product_id]['quantity'] + int(quantity)
                    new_price =  Decimal(str(product['price'])) * int(quantity)

                    print('updating alredy exiting product')
                    
                    table.update_item(
                        Key={
                            'user_id': user_id,
                            'cart_id': cart_id
                        },
                        UpdateExpression='SET products.#product_id.quantity = :quantity, products.#product_id.price = :price, updated_at = :updated_at',
                        ExpressionAttributeNames={
                            '#product_id': product_id
                        },
                        ExpressionAttributeValues={
                            ':quantity': quantity,
                            ':price': new_price,
                            ':updated_at': current_time
                        }
                    )
                else:
                    # Add new product to existing cart
                    table.update_item(
                        Key={
                            'user_id': user_id,
                            'cart_id': cart_id
                        },
                        UpdateExpression='SET products.#product_id = :product, updated_at = :updated_at',
                        ExpressionAttributeNames={
                            '#product_id': product_id
                        },
                        ExpressionAttributeValues={
                            ':product': {
                                'quantity': int(quantity),
                                'price': Decimal(str(price))
                            },
                            ':updated_at': current_time
                        }
                    )
            else:
                # Create new cart for user
                print('creating new cart for user')
                cart_id = f"cart_{user_id}"  # Deterministic cart ID based on user_id
                item = {
                    'user_id': user_id,
                    'cart_id': cart_id,
                    'products': {
                        product_id: {
                            'quantity': quantity,
                            'price': price
                        }
                    },
                    'order_id': None,
                    'created_at': current_time,
                    'updated_at': current_time
                }

                item = Cart.from_dict(item)
                table.put_item(Item=item.to_dict())
                print('insert_successful')
            
            # Enhance response with product details
            response_data = {
                'user_id': user_id,
                'cart_id': cart_id,
                'product': product,
                'quantity': quantity,
                'price': price
            }
           
            return jsonify(response_data), 200
            
        except Exception as e:
            print('raising expection while cart creation..')
            print(e)
            return jsonify({'error': str(e)}), 500
        
    @staticmethod
    def get_cart_by_user_id( user_id):
        try:
            dynamodb = DynamoDBConn.get_connection()
            table = dynamodb.Table('Cart')
            
            response = table.get_item(Key={'cart_id': 'cart_'+user_id, 'user_id': user_id })

            print(response)
            
            if 'Item' not in response:
                return jsonify({'error': 'Cart not found'}), 404
                
            cart_item = response['Item']
            cart_products = []
            total_price = Decimal('0')
            failed_products = []
            
            for product_id, product_details in cart_item.get('products', {}).items():
                try:
                    product = get_product_details(product_id)
                    if product:
                        product_info = {
                            'product': product,
                            'quantity': product_details['quantity'],
                            'price': float(product_details['price'])
                        }
                        cart_products.append(product_info)
                        total_price += Decimal(str(product_details['price']))
                    else:
                        failed_products.append(product_id)
                except Exception as e:
                    print(f"Error fetching product {product_id}: {str(e)}")
                    failed_products.append(product_id)
            
            response_data = {
                'user_id': cart_item['user_id'],
                'cart_id': cart_item['cart_id'],
                'items': cart_products,
                'total_price': float(total_price),
                'created_at': cart_item.get('created_at'),
                'updated_at': cart_item.get('updated_at')
            }
            
            if failed_products:
                response_data['failed_products'] = failed_products
            
            return jsonify(response_data), 200
            
        except Exception as e:
            print(f'Error details: {str(e)}')
            return jsonify({'error': str(e)}), 500
        
    @staticmethod
    def update_cart(user_id, cart_data):
        try:
            product_id = cart_data.get('product_id')
            quantity = int(cart_data.get('quantity', 0))
            current_time = datetime.now(timezone.utc).isoformat()
            
            if quantity < 0:
                return jsonify({'error': 'Quantity cannot be negative'}), 400
                
            dynamodb = DynamoDBConn.get_connection()
            table = dynamodb.Table('Cart')
            
            # Generate cart_id
            cart_id = f"cart_{user_id}"
            
            # First get the current cart item
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            if 'Item' not in response:
                return jsonify({'error': 'Cart not found'}), 404
                
            cart_item = response['Item']
            
            # Get product details to calculate new price
            product = get_product_details(product_id)
            if product is None:
                return jsonify({'error': 'Product not found'}), 404
                
            new_price = Decimal(str(product['price'] * quantity))
            
            if quantity == 0:
                # Remove product from cart if quantity is 0
                table.update_item(
                    Key={
                        'user_id': user_id,
                        'cart_id': cart_id
                    },
                    UpdateExpression='REMOVE products.#pid SET updated_at = :uat',
                    ExpressionAttributeNames={
                        '#pid': product_id
                    },
                    ExpressionAttributeValues={
                        ':uat': current_time
                    }
                )
            else:
                # Update product quantity and price
                table.update_item(
                    Key={
                        'user_id': user_id,
                        'cart_id': cart_id
                    },
                    UpdateExpression='SET products.#pid = :product, updated_at = :uat',
                    ExpressionAttributeNames={
                        '#pid': product_id
                    },
                    ExpressionAttributeValues={
                        ':product': {
                            'quantity': quantity,
                            'price': new_price
                        },
                        ':uat': current_time
                    }
                )
            
            # Get updated cart for response
            updated_response = table.get_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            if 'Item' not in updated_response:
                return jsonify({'error': 'Failed to retrieve updated cart'}), 500
                
            updated_cart = updated_response['Item']
            
            # Calculate new total and prepare response
            cart_products = []
            total_price = Decimal('0')
            
            for pid, details in updated_cart.get('products', {}).items():
                prod = get_product_details(pid)
                if prod:
                    product_info = {
                        'product': prod,
                        'quantity': details['quantity'],
                        'price': float(details['price'])
                    }
                    cart_products.append(product_info)
                    total_price += Decimal(str(details['price']))
            
            response_data = {
                'user_id': user_id,
                'cart_id': cart_id,
                'items': cart_products,
                'total_price': float(total_price),
                'updated_at': current_time
            }
            
            return jsonify(response_data), 200
            
        except Exception as e:
            print(f"Error updating cart: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @staticmethod
    def delete_item(user_id, product_id):
        try:
            dynamodb = DynamoDBConn.get_connection()
            table = dynamodb.Table('Cart')
            
            # Generate cart_id
            cart_id = f"cart_{user_id}"
            
            # First check if the cart and product exist
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            if 'Item' not in response:
                return jsonify({'error': 'Cart not found'}), 404
                
            cart_item = response['Item']
            
            if product_id not in cart_item.get('products', {}):
                return jsonify({'error': 'Product not found in cart'}), 404
                
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Remove the specific product from the products map
            table.update_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                },
                UpdateExpression='REMOVE products.#product_id SET updated_at = :updated_at',
                ExpressionAttributeNames={
                    '#product_id': product_id
                },
                ExpressionAttributeValues={
                    ':updated_at': current_time
                }
            )
            
            # Get updated cart for response
            updated_response = table.get_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            if 'Item' not in updated_response:
                return jsonify({'error': 'Failed to retrieve updated cart'}), 500
                
            updated_cart = updated_response['Item']
            
            # Calculate new total and prepare response
            cart_products = []
            total_price = Decimal('0')
            
            for pid, details in updated_cart.get('products', {}).items():
                prod = get_product_details(pid)
                if prod:
                    product_info = {
                        'product': prod,
                        'quantity': details['quantity'],
                        'price': float(details['price'])
                    }
                    cart_products.append(product_info)
                    total_price += Decimal(str(details['price']))
            
            response_data = {
                'user_id': user_id,
                'cart_id': cart_id,
                'items': cart_products,
                'total_price': float(total_price),
                'updated_at': current_time,
                'message': f'Product {product_id} removed from cart successfully'
            }
            
            return jsonify(response_data), 200
            
        except Exception as e:
            print(f"Error deleting item from cart: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @staticmethod
    def delete_cart(user_id):
        try:
            dynamodb = DynamoDBConn.get_connection()
            table = dynamodb.Table('Cart')
            
            # Generate cart_id
            cart_id = f"cart_{user_id}"
            
            # First check if the cart exists
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            if 'Item' not in response:
                return jsonify({'error': 'Cart not found'}), 404
                
            # Delete the cart using both primary key components
            table.delete_item(
                Key={
                    'user_id': user_id,
                    'cart_id': cart_id
                }
            )
            
            return jsonify({
                'message': 'Cart deleted successfully',
                'user_id': user_id,
                'cart_id': cart_id,
                'deleted_at': datetime.now(timezone.utc).isoformat()
            }), 200
                
        except Exception as e:
            print(f"Error deleting cart: {str(e)}")
            return jsonify({'error': str(e)}), 500
    

    # Request validation functions
    def validate_cart_data(data):
        """Validate cart creation/update request data"""

        print('validating data')
        if not isinstance(data, dict):
            raise ValueError("Invalid request format")
            
        if 'product_id' not in data:
            raise ValueError("Product ID is required")
            
        quantity = data.get('quantity', 0)
        print(data, quantity)
        try:
            quantity = int(quantity)
            if quantity < 0:
                raise ValueError("Quantity cannot be negative")
            if quantity > 99:
                raise ValueError("Quantity exceeds maximum limit of 99")
        except (ValueError, TypeError):
            raise ValueError("Invalid quantity value")
            
        return True