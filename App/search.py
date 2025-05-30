import json
from typing import List, Dict, Any, Optional
from opensearchpy import OpenSearch
from .config import settings
from .models import Property, PropertySearchRequest, PropertySearchResponse, PropertySearchFilters

class PropertySearchEngine:
    def __init__(self):
        self.client = self._create_client()
        self.index_name = settings.OPENSEARCH_INDEX
    
    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client"""
        return OpenSearch(
            hosts=[{
                'host': settings.OPENSEARCH_HOST,
                'port': settings.OPENSEARCH_PORT
            }],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=False,
            ssl_show_warn=False
        )
    
    def create_index(self):
        """Create properties index with mapping"""
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "standard"},
                    "description": {"type": "text", "analyzer": "standard"},
                    "price": {"type": "float"},
                    "location": {
                        "properties": {
                            "address": {"type": "text"},
                            "city": {"type": "keyword"},
                            "state": {"type": "keyword"},
                            "zip_code": {"type": "keyword"},
                            "latitude": {"type": "float"},
                            "longitude": {"type": "float"},
                            "neighborhood": {"type": "keyword"}
                        }
                    },
                    "details": {
                        "properties": {
                            "bedrooms": {"type": "integer"},
                            "bathrooms": {"type": "float"},
                            "square_feet": {"type": "integer"},
                            "lot_size": {"type": "float"},
                            "year_built": {"type": "integer"},
                            "property_type": {"type": "keyword"},
                            "parking": {"type": "keyword"},
                            "amenities": {"type": "keyword"}
                        }
                    },
                    "status": {"type": "keyword"},
                    "listing_date": {"type": "date"},
                    "images": {"type": "keyword"},
                    "agent_contact": {"type": "keyword"}
                }
            }
        }
        
        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name, body=mapping)
    
    def add_property(self, property_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a single property to the index"""
        response = self.client.index(
            index=self.index_name,
            id=property_data.get('id'),
            body=property_data
        )
        return response
    
    def update_property(self, property_id: str, property_data: Dict[str, Any]) -> bool:
        """Update an existing property"""
        try:
            response = self.client.update(
                index=self.index_name,
                id=property_id,
                body={"doc": property_data}
            )
            return response['result'] in ['updated', 'noop']
        except Exception:
            return False
    
    def delete_property(self, property_id: str) -> bool:
        """Delete a property"""
        try:
            response = self.client.delete(
                index=self.index_name,
                id=property_id
            )
            return response['result'] == 'deleted'
        except Exception:
            return False
    
    def get_property_by_id(self, property_id: str) -> Optional[Property]:
        """Get a property by ID"""
        try:
            response = self.client.get(
                index=self.index_name,
                id=property_id
            )
            return Property(**response['_source'])
        except Exception:
            return None
    
    def bulk_index_properties(self, properties: List[Dict[str, Any]]):
        """Bulk index multiple properties"""
        from opensearchpy.helpers import bulk
        
        actions = []
        for prop in properties:
            actions.append({
                "_index": self.index_name,
                "_id": prop.get('id'),
                "_source": prop
            })
        
        bulk(self.client, actions)
    
    def search_properties(self, search_request: PropertySearchRequest) -> PropertySearchResponse:
        """Search properties based on request parameters"""
        query = self._build_search_query(search_request)
        
        # Calculate pagination
        from_offset = (search_request.page - 1) * search_request.limit
        
        # Execute search
        response = self.client.search(
            index=self.index_name,
            body={
                "query": query,
                "from": from_offset,
                "size": search_request.limit,
                "sort": self._build_sort_criteria(search_request.sort_by, search_request.sort_order)
            }
        )
        
        # Parse results
        properties = []
        for hit in response['hits']['hits']:
            properties.append(Property(**hit['_source']))
        
        total = response['hits']['total']['value']
        total_pages = (total + search_request.limit - 1) // search_request.limit
        
        return PropertySearchResponse(
            properties=properties,
            total=total,
            page=search_request.page,
            limit=search_request.limit,
            total_pages=total_pages
        )
    
    def _build_search_query(self, search_request: PropertySearchRequest) -> Dict[str, Any]:
        """Build OpenSearch query from search request"""
        must_clauses = []
        filter_clauses = []
        
        # Text search
        if search_request.query:
            must_clauses.append({
                "multi_match": {
                    "query": search_request.query,
                    "fields": ["title^2", "description", "location.address", "location.city", "location.neighborhood"]
                }
            })
        
        # Filters
        if search_request.filters:
            filters = search_request.filters
            
            # Location filter
            if filters.location:
                must_clauses.append({
                    "multi_match": {
                        "query": filters.location,
                        "fields": ["location.city", "location.state", "location.address", "location.neighborhood"]
                    }
                })
            
            # Price range
            if filters.min_price or filters.max_price:
                price_range = {}
                if filters.min_price:
                    price_range["gte"] = filters.min_price
                if filters.max_price:
                    price_range["lte"] = filters.max_price
                
                filter_clauses.append({
                    "range": {"price": price_range}
                })
            
            # Bedrooms
            if filters.bedrooms:
                filter_clauses.append({
                    "term": {"details.bedrooms": filters.bedrooms}
                })
            
            # Bathrooms
            if filters.bathrooms:
                filter_clauses.append({
                    "range": {"details.bathrooms": {"gte": filters.bathrooms}}
                })
            
            # Property type
            if filters.property_type:
                filter_clauses.append({
                    "term": {"details.property_type": filters.property_type}
                })
            
            # Square footage
            if filters.min_sqft or filters.max_sqft:
                sqft_range = {}
                if filters.min_sqft:
                    sqft_range["gte"] = filters.min_sqft
                if filters.max_sqft:
                    sqft_range["lte"] = filters.max_sqft
                
                filter_clauses.append({
                    "range": {"details.square_feet": sqft_range}
                })
        
        # Only active properties
        filter_clauses.append({
            "term": {"status": "active"}
        })
        
        # Build final query
        if must_clauses or filter_clauses:
            return {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses
                }
            }
        else:
            return {"match_all": {}}
    
    def _build_sort_criteria(self, sort_by: str, sort_order: str) -> List[Dict[str, Any]]:
        """Build sort criteria for OpenSearch"""
        sort_map = {
            "price": "price",
            "date": "listing_date",
            "bedrooms": "details.bedrooms",
            "sqft": "details.square_feet",
            "relevance": "_score"
        }
        
        field = sort_map.get(sort_by, "price")
        order = "desc" if sort_order == "desc" else "asc"
        
        # Special handling for relevance score
        if field == "_score":
            return [{"_score": {"order": "desc"}}]
        
        return [{field: {"order": order}}]
    
    def get_location_suggestions(self, query: str, limit: int = 10) -> List[str]:
        """Get location suggestions based on query"""
        search_query = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "location.city": {
                                    "query": query,
                                    "boost": 2
                                }
                            }
                        },
                        {
                            "match": {
                                "location.neighborhood": query
                            }
                        },
                        {
                            "match": {
                                "location.state": query
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "unique_cities": {
                    "terms": {
                        "field": "location.city",
                        "size": limit
                    }
                },
                "unique_neighborhoods": {
                    "terms": {
                        "field": "location.neighborhood",
                        "size": limit
                    }
                }
            },
            "size": 0
        }
        
        try:
            response = self.client.search(index=self.index_name, body=search_query)
            
            suggestions = []
            
            # Add cities
            for bucket in response['aggregations']['unique_cities']['buckets']:
                if query.lower() in bucket['key'].lower():
                    suggestions.append(bucket['key'])
            
            # Add neighborhoods
            for bucket in response['aggregations']['unique_neighborhoods']['buckets']:
                if bucket['key'] and query.lower() in bucket['key'].lower():
                    suggestions.append(bucket['key'])
            
            return list(set(suggestions))[:limit]
        except Exception:
            return []
    
    def get_location_trends(self, location: str, property_type: Optional[str] = None, time_period: str = "1year") -> Dict[str, Any]:
        """Get location trends data"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": location,
                                "fields": ["location.city", "location.state", "location.neighborhood"]
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "avg_price": {"avg": {"field": "price"}},
                "median_price": {"percentiles": {"field": "price", "percents": [50]}},
                "min_price": {"min": {"field": "price"}},
                "max_price": {"max": {"field": "price"}},
                "total_properties": {"value_count": {"field": "id"}},
                "price_per_sqft": {
                    "avg": {
                        "script": {
                            "source": "if (doc['details.square_feet'].size() > 0 && doc['details.square_feet'].value > 0) { return doc['price'].value / doc['details.square_feet'].value } else { return 0 }"
                        }
                    }
                },
                "property_types": {"terms": {"field": "details.property_type"}},
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"key": "Under $200K", "to": 200000},
                            {"key": "$200K-$400K", "from": 200000, "to": 400000},
                            {"key": "$400K-$600K", "from": 400000, "to": 600000},
                            {"key": "$600K-$800K", "from": 600000, "to": 800000},
                            {"key": "Over $800K", "from": 800000}
                        ]
                    }
                },
                "bedrooms_distribution": {"terms": {"field": "details.bedrooms"}},
                "listing_dates": {
                    "date_histogram": {
                        "field": "listing_date",
                        "calendar_interval": "month"
                    }
                }
            }
        }
        
        # Add property type filter if specified
        if property_type:
            query["query"]["bool"]["must"].append({
                "term": {"details.property_type": property_type}
            })
        
        try:
            response = self.client.search(index=self.index_name, body=query, size=0)
            aggs = response['aggregations']
            
            return {
                "location": location,
                "property_type": property_type,
                "time_period": time_period,
                "summary": {
                    "total_properties": aggs['total_properties']['value'],
                    "average_price": aggs['avg_price']['value'] or 0,
                    "median_price": list(aggs['median_price']['values'].values())[0] if aggs['median_price']['values'] else 0,
                    "min_price": aggs['min_price']['value'] or 0,
                    "max_price": aggs['max_price']['value'] or 0,
                    "avg_price_per_sqft": aggs['price_per_sqft']['value'] or 0,
                    "property_types": [
                        {"type": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['property_types']['buckets']
                    ],
                    "price_ranges": [
                        {"range": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['price_ranges']['buckets']
                    ],
                    "bedrooms_distribution": [
                        {"bedrooms": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['bedrooms_distribution']['buckets']
                    ],
                    "monthly_listings": [
                        {"month": bucket['key_as_string'], "count": bucket['doc_count']} 
                        for bucket in aggs['listing_dates']['buckets']
                    ]
                }
            }
        except Exception as e:
            print(f"Error getting location trends: {e}")
            return {
                "location": location,
                "property_type": property_type,
                "time_period": time_period,
                "summary": {
                    "total_properties": 0,
                    "average_price": 0,
                    "median_price": 0,
                    "min_price": 0,
                    "max_price": 0,
                    "avg_price_per_sqft": 0,
                    "property_types": [],
                    "price_ranges": [],
                    "bedrooms_distribution": [],
                    "monthly_listings": []
                }
            }
    
    def get_property_stats(self, location: Optional[str] = None, property_type: Optional[str] = None) -> Dict[str, Any]:
        """Get property statistics for analytics"""
        query = {"query": {"match_all": {}}}
        
        # Add filters if provided
        filters = []
        if location:
            filters.append({
                "multi_match": {
                    "query": location,
                    "fields": ["location.city", "location.state", "location.neighborhood"]
                }
            })
        
        if property_type:
            filters.append({
                "term": {"details.property_type": property_type}
            })
        
        if filters:
            query = {
                "query": {
                    "bool": {
                        "must": filters
                    }
                }
            }
        
        # Add aggregations
        query["aggs"] = {
            "total_properties": {"value_count": {"field": "id"}},
            "avg_price": {"avg": {"field": "price"}},
            "price_stats": {"stats": {"field": "price"}},
            "sqft_stats": {"stats": {"field": "details.square_feet"}},
            "property_types": {"terms": {"field": "details.property_type", "size": 20}},
            "cities": {"terms": {"field": "location.city", "size": 20}},
            "bedrooms": {"terms": {"field": "details.bedrooms"}},
            "bathrooms": {"terms": {"field": "details.bathrooms"}},
            "status_distribution": {"terms": {"field": "status"}}
        }
        
        try:
            response = self.client.search(index=self.index_name, body=query, size=0)
            aggs = response['aggregations']
            
            return {
                "filters": {
                    "location": location,
                    "property_type": property_type
                },
                "statistics": {
                    "total_properties": aggs['total_properties']['value'],
                    "price_statistics": aggs['price_stats'],
                    "square_feet_statistics": aggs['sqft_stats'],
                    "property_types": [
                        {"type": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['property_types']['buckets']
                    ],
                    "top_cities": [
                        {"city": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['cities']['buckets']
                    ],
                    "bedrooms_distribution": [
                        {"bedrooms": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['bedrooms']['buckets']
                    ],
                    "bathrooms_distribution": [
                        {"bathrooms": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['bathrooms']['buckets']
                    ],
                    "status_distribution": [
                        {"status": bucket['key'], "count": bucket['doc_count']} 
                        for bucket in aggs['status_distribution']['buckets']
                    ]
                }
            }
        except Exception as e:
            print(f"Error getting property stats: {e}")
            return {
                "filters": {"location": location, "property_type": property_type},
                "statistics": {
                    "total_properties": 0,
                    "price_statistics": {},
                    "square_feet_statistics": {},
                    "property_types": [],
                    "top_cities": [],
                    "bedrooms_distribution": [],
                    "bathrooms_distribution": [],
                    "status_distribution": []
                }
            }
    
    def update_location_trends(self, location: str):
        """Update location trends (placeholder for background task)"""
        # This would typically update cached trend data
        print(f"Updating location trends for: {location}")
    
    def update_market_stats(self, location: str):
        """Update market statistics (placeholder for background task)"""
        # This would typically update cached market statistics
        print(f"Updating market stats for: {location}")

# Global search engine instance
search_engine = PropertySearchEngine()