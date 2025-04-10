import requests
import os

CART_SERVICE_URL = 'http://cart-service-ecs-connect:5003'

def get_cart_items(auth_header):
    """Fetch cart items from cart service"""
    print('inget cart items', auth_header)
    try:
        headers = {}
        if auth_header:
            headers['Authorization'] = auth_header

        response = requests.get(
            f"{CART_SERVICE_URL}/cart/user_cart",
            headers=headers,
            timeout=20  # Add timeout for better error handling
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            response.raise_for_status()
            
    except requests.RequestException as e:
        print(f"Error fetching cart items: {str(e)}")
        raise Exception(f"Failed to fetch cart items: {str(e)}")

def delete_cart(auth_header):
    """Delete cart after order is placed"""
    try:
        headers = {}
        if auth_header:
            headers['Authorization'] = auth_header

        response = requests.delete(
            f"{CART_SERVICE_URL}/cart/delete",
            headers=headers,
            timeout=20  # Add timeout for better error handling
        )
    
        if response.status_code != 200:
            raise Exception(f"Failed to delete cart: {response.text}")
    except requests.RequestException as e:
        raise Exception(f"Cart service error: {str(e)}")
    
def calculate_order_total(cart_items):
    """Calculate total amount from cart items"""
    return sum(float(item['price']) * float(item['quantity']) for item in cart_items)