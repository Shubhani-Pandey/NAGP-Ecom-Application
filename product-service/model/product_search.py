from flask import Flask, request, jsonify
from flask_cors import CORS
from http import HTTPStatus
from typing import Dict, Any
from model.product_search_utils import ProductSearch

class SearchAPI:

    def __init__(self):
        self.product_search = ProductSearch()

    # params: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    def validate_search_params(self, params):
        """Validate and clean search parameters"""
        try:
            clean_params = {}
            
            # Text search parameter
            if 'q' in params:
                clean_params['search_term'] = str(params['q']).strip()

            # Numeric parameters
            if 'price_ranges' in params:
                clean_params['price_ranges'] = params['price_ranges']
            
            # Pagination
            clean_params['page'] = int(params.get('page', 1))
            if clean_params['page'] < 1:
                return None, "Page number must be greater than 0"
            
            clean_params['size'] = int(params.get('size', 20))
            if clean_params['size'] < 1 or clean_params['size'] > 100:
                return None, "Size must be between 1 and 100"

            # Sorting
            if 'sort_by' in params:
                allowed_sort_fields = ['price', 'created_at', '_score', 'name.keyword']
                if params['sort_by'] not in allowed_sort_fields:
                    return None, f"Sort field must be one of {allowed_sort_fields}"
                clean_params['sort_by'] = params['sort_by']
                clean_params['sort_order'] = params.get('sort_order', 'desc').lower()
                if clean_params['sort_order'] not in ['asc', 'desc']:
                    return None, "Sort order must be 'asc' or 'desc'"

            # Filters
            if 'category_id' in params:
                clean_params['category_id'] = str(params['category_id'])
            
            if 'brand_name' in params:
                clean_params['brand_name'] = str(params['brand_name'])

            # Fuzzy search parameters
            if 'fuzziness' in params:
                if params['fuzziness'] not in ['AUTO', '0', '1', '2']:
                    return None, "Fuzziness must be 'AUTO', '0', '1', or '2'"
                clean_params['fuzziness'] = params['fuzziness']

            return clean_params, None
            
        except ValueError as e:
            return None, f"Invalid parameter value: {str(e)}"
        except Exception as e:
            return None, f"Error processing parameters: {str(e)}"

    def format_response(self, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """Format search results for API response"""
        try:
            products = []
            for hit in search_results['hits']:
                product = hit['_source']
                product.update({
                    'score': hit['_score'],
                    'highlights': hit.get('highlight', {})
                })
                products.append(product)

            response = {
                'products': products,
                'metadata': {
                    'total': search_results['total'],
                    'page': search_results['page'],
                    'size': search_results['size'],
                    'total_pages': (search_results['total'] + search_results['size'] - 1) 
                                 // search_results['size']
                },
                'aggregations': {
                    'price_ranges': search_results['aggregations']['price_ranges']['buckets'],
                    'brands': search_results['aggregations']['brands']['buckets'],
                    'categories': search_results['aggregations']['categories']['buckets']
                }
            }
            return response
        except Exception as e:
            raise Exception(f"Error formatting response: {str(e)}")
