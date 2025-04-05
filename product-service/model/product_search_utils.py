from model.product import ProductModel
import json

class ProductSearch:
    def __init__(self):
        self.client = ProductModel.get_opensearch_client()
        # self.cache = SearchCache()

    def build_fuzzy_query(self, search_term, fields=None, fuzzy_params=None):
        """
        Build a comprehensive fuzzy search query
        """
    

        if fuzzy_params is None:
            fuzzy_params = {
                "fuzziness": "AUTO",
                "prefix_length": 3,
                "max_expansions": 20
            }

        if fields is None:
            fields = [
                "name^5",         
                "brand_name^4",    
                "category_name^4",
                "tags^3",       
                "description^0.2"   
            ]

        return {
                "bool": {
                    "should": [ 
                        {
                            "multi_match": {
                                "query": search_term,
                                "fields": fields,
                                "type": "most_fields",  
                                "operator": "and",       
                                "minimum_should_match": "90%" 
                            }
                        },
                        {
                            "multi_match": {
                                "query": search_term,
                                "fields": ["name^3", "brand_name^2", "category_name^2"],
                                "type": "phrase",
                                "slop": 1,  
                                "boost": 2 
                            }
                        },
                        {
                            "multi_match": {
                                "query": search_term,
                                "fields": ["name^2"],
                                "type": "phrase_prefix",
                                "slop": 1,
                                "max_expansions": 10,  
                                "boost": 1.5
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            }


    def search_products(self, query_params):
        """
        Enhanced search with fuzzy matching
        """
        try:
            # # Check cache first
            # cached_results = self.cache.get_cached_results(query_params)
            # if cached_results:
            #     return cached_results

            search_query = {
                "bool": {
                    "must": [],
                    "filter": []
                }
            }

            # Text search with fuzzy matching
            if query_params.get('search_term'):
                search_term = query_params['search_term']
                fuzzy_params = {
                    "fuzziness": query_params.get('fuzziness', 'AUTO'),
                    "prefix_length": int(query_params.get('prefix_length', 2)),
                    "max_expansions": int(query_params.get('max_expansions', 50))
                }
                
                search_query["bool"]["must"].append(
                    self.build_fuzzy_query(search_term, fuzzy_params=fuzzy_params)
                )
            print('after search filter',search_query)

            # Add category filter
            if query_params.get('category_id'):
                search_query["bool"]["filter"].append(
                    {"match": {"category_id": query_params['category_id']}}
                )

            # Add filters
            if query_params.get('price_ranges'):
                # Parse the price ranges if it's a string
                if isinstance(query_params['price_ranges'], str):
                    price_ranges = json.loads(query_params['price_ranges'])
                else:
                    price_ranges = query_params['price_ranges']

                # Create a bool query with should clauses for price ranges
                price_filter = {
                    "bool": {
                        "should": []
                    }
                }

                # Add each price range to the should clause
                for price_range in price_ranges:
                    range_query = {
                        "range": {
                            "price": {}
                        }
                    }
                    
                    if price_range.get('min') is not None:
                        range_query["range"]["price"]["gte"] = float(price_range['min'])
                    if price_range.get('max') is not None:
                        range_query["range"]["price"]["lte"] = float(price_range['max'])
                        
                    price_filter["bool"]["should"].append(range_query)

                # Add minimum_should_match to ensure at least one range matches
                price_filter["bool"]["minimum_should_match"] = 1
                
                # Add the price filter to the main query
                search_query["bool"]["filter"].append(price_filter)

            # Build complete search body
            search_body = {
                # "min_score": 0.5,
                "query": search_query,
                "aggs": {
                    "price_ranges": {
                        "range": {
                            "field": "price",
                            "ranges": [
                                {"to": 100},
                                {"from": 100, "to": 500},
                                {"from": 500, "to": 1000},
                                {"from": 1000, "to": 4000},
                                {"from": 4000, "to": 10000},
                                {"from": 10000}
                            ]
                        }
                    },
                    "brands": {
                        "terms": {"field": "brand_name.keyword",
                                  "size": 50 }
                    },
                    "categories": {
                        "terms": {"field": "category_id",
                                  "size": 20}
                    }
                },
                "highlight": {
                    "fields": {
                        "name": {"pre_tags": ["<em>"], "post_tags": ["</em>"]},
                        "description": {"pre_tags": ["<em>"], "post_tags": ["</em>"]},
                        "brand_name": {"pre_tags": ["<em>"], "post_tags": ["</em>"]}
                    }
                }
            }

            # Add sorting
            sort_field = query_params.get('sort_by', '_score')
            sort_order = query_params.get('sort_order', 'desc')
            search_body["sort"] = [{sort_field: {"order": sort_order}}]

            # Add pagination
            page = int(query_params.get('page', 1))
            size = int(query_params.get('size', 20))
            search_body["from"] = (page - 1) * size
            search_body["size"] = size

            print(search_body)

            # Execute search
            response = self.client.search(
                index='products',
                body=search_body,
                explain=True
            )

            print("*********************************************************")
            print(response)

            results = {
                'hits': response['hits']['hits'],
                'total': response['hits']['total']['value'],
                'aggregations': response['aggregations'],
                'page': page,
                'size': size
            }

            # # Cache results
            # self.cache.cache_results(query_params, results)

            return results

        except Exception as e:
            print(f"Search error: {str(e)}")
            raise e

    def suggest_products(self, prefix: str, size: int = 5) -> list:
        """
        Get search suggestions using multiple suggestion strategies
        """
        try:
            # # Check cache first
            # cache_key = f"suggest:{prefix}:{size}"
            # cached_suggestions = self.cache.get_cached_results(cache_key)
            # if cached_suggestions:
            #     return cached_suggestions

            # Build suggestion query
            suggest_body = {
                # Completion suggester for product names
                "name_completion": {
                    "prefix": prefix,
                    "completion": {
                        "field": "name.completion",
                        "size": size,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO",
                            "min_length": 3
                        }
                    }
                },
                # Phrase suggester for spell checking
                "name_phrase": {
                    "text": prefix,
                    "phrase": {
                        "field": "name.fuzzy",
                        "size": size,
                        "gram_size": 3,
                        "confidence": 0.0,
                        "max_errors": 2,
                        "direct_generator": [{
                            "field": "name.fuzzy",
                            "suggest_mode": "always"
                        }],
                        "highlight": {
                            "pre_tag": "<em>",
                            "post_tag": "</em>"
                        }
                    }
                },
                # Term suggester for similar terms
                "name_term": {
                    "text": prefix,
                    "term": {
                        "field": "name.fuzzy",
                        "suggest_mode": "always",
                        "sort": "frequency",
                        "size": size
                    }
                }
            }

            # Execute suggestion query
            response = self.client.search(
                index='products',
                body={
                    "suggest": suggest_body,
                    "_source": ["name", "brand_name", "price", "category_id"],
                    "size": 0  # We don't need search results
                }
            )

            # Process suggestions
            suggestions = self._process_suggestions(response, prefix, size)

            # # Cache results
            # self.cache.cache_results(cache_key, suggestions, ttl=300)  # Cache for 5 minutes

            return suggestions

        except Exception as e:
            print(f"Suggestion error: {str(e)}")
            raise e

    def _process_suggestions(self, response: dict, prefix: str, size: int) -> list:
        """
        Process and combine different types of suggestions
        """
        results = []
        seen = set()

        # Process completion suggestions (highest priority)
        if 'name_completion' in response['suggest']:
            for suggestion in response['suggest']['name_completion'][0]['options']:
                if len(results) >= size:
                    break
                
                source = suggestion['_source']
                text = source['name']
                
                if text.lower() not in seen:
                    results.append({
                        'text': text,
                        'type': 'completion',
                        'score': suggestion['_score'],
                        'metadata': {
                            'brand': source.get('brand_name'),
                            'price': source.get('price'),
                            'category_id': source.get('category_id')
                        }
                    })
                    seen.add(text.lower())

        # Process phrase suggestions (medium priority)
        if 'name_phrase' in response['suggest']:
            for suggestion in response['suggest']['name_phrase'][0]['options']:
                if len(results) >= size:
                    break
                
                text = suggestion['text']
                if text.lower() not in seen:
                    results.append({
                        'text': text,
                        'type': 'phrase',
                        'score': suggestion['score'],
                        'highlighted': suggestion.get('highlighted', text)
                    })
                    seen.add(text.lower())

        # Process term suggestions (lowest priority)
        if 'name_term' in response['suggest']:
            for suggestion in response['suggest']['name_term'][0]['options']:
                if len(results) >= size:
                    break
                
                text = suggestion['text']
                if text.lower() not in seen:
                    results.append({
                        'text': text,
                        'type': 'term',
                        'score': suggestion['score']
                    })
                    seen.add(text.lower())

        # Add popular searches if we have space
        if len(results) < size:
            popular_searches = self._get_popular_searches(prefix, size - len(results))
            for search in popular_searches:
                if search['text'].lower() not in seen:
                    results.append(search)
                    seen.add(search['text'].lower())

        return results[:size]

    def _get_popular_searches(self, prefix: str, size: int) -> list:
        """
        Get popular searches starting with the prefix
        """
        try:
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "prefix": {
                                    "name.keyword": prefix.lower()
                                }
                            }
                        ]
                    }
                },
                "aggs": {
                    "popular_searches": {
                        "terms": {
                            "field": "name.keyword",
                            "size": size,
                            "order": {
                                "_count": "desc"
                            }
                        }
                    }
                },
                "size": 0
            }

            response = self.client.search(
                index='products',
                body=query
            )

            popular = []
            for bucket in response['aggregations']['popular_searches']['buckets']:
                popular.append({
                    'text': bucket['key'],
                    'type': 'popular',
                    'score': bucket['doc_count']
                })

            return popular

        except Exception as e:
            print(f"Error getting popular searches: {str(e)}")
            return []