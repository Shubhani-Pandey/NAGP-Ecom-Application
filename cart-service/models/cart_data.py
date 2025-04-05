from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

@dataclass
class Cart:
    user_id:str
    cart_id: str
    products: dict
    # price: Decimal
    # quantity: int
    order_id: Optional[str] = ''
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


    @classmethod
    def from_dict(cls, data: dict):
        # Handle products conversion
        products = data.get('products', {})
        
        # If products is a string representation of a dict, convert it
        if isinstance(products, str):
            try:
                import json
                products = json.loads(products)
            except json.JSONDecodeError:
                products = {}
        
        # Convert product prices to Decimal if they're not already
        converted_products = {}
        for prod_id, prod_details in products.items():
                converted_products[prod_id] = {
                    'quantity': int(prod_details.get('quantity', 0)),
                    'price': Decimal(str(prod_details.get('price', '0')))
                }
        
        return cls(
            user_id=str(data.get('user_id', '')),
            cart_id=str(data.get('cart_id', '')),
            products=converted_products,
            order_id=str(data.get('order_id', '')) if data.get('order_id') else None,
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    
    def to_dict(self):
        return {
            'user_id':self.user_id,
            'cart_id': self.cart_id,
            'products': self.products,
            'order_id': self.order_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }