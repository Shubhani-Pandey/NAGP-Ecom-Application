from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

@dataclass
class Product:
    product_id: str
    name: str
    price: Decimal
    stock: int
    category_id: str
    brand_name: str
    description: Optional[str] = ''
    product_image_url: Optional[str] = ''
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


    @classmethod
    def from_dict(cls, data: dict):
        if 'price' in data and not isinstance(data['price'], Decimal):
            data['price'] = Decimal(str(data['price']))
        return cls(**data)

    def to_dict(self):
        return {
            'product_id': self.product_id,
            'name': self.name,
            'price': self.price,
            'stock': self.stock,
            'category_id': self.category_id,
            'description': self.description,
            'product_image_url': self.product_image_url,
            'brand_name': self.brand_name,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }