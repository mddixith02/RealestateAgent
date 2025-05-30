import json
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .config import settings
from .models import Property, PropertySearchRequest, PropertySearchFilters, ChatResponse
from .search import search_engine
from .prompts import (
    REAL_ESTATE_AGENT_PROMPT,
    PROPERTY_SEARCH_PROMPT,
    PROPERTY_RECOMMENDATION_PROMPT
)

class RealEstateAgent:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.conversation_history = {}
        self.user_favorites = {}

    async def process_message(self, message: str, user_id: Optional[str] = None,
                              session_id: Optional[str] = None,
                              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process user message and return agent response"""
        try:
            search_criteria = await self._extract_search_criteria(message)
            properties = []
            if search_criteria and any(search_criteria.values()):
                properties = await self._search_properties(search_criteria)

            agent_response = await self._generate_response(message, context, properties)
            suggestions = await self._generate_suggestions(message, properties)

            # Store in chat history
            if session_id:
                self._store_chat_history(session_id, "user", message)
                self._store_chat_history(session_id, "agent", agent_response)

            return {
                "response": agent_response,
                "properties": properties[:5] if properties else None,
                "suggestions": suggestions,
                "session_id": session_id,
                "requires_action": False,
                "action_type": None
            }

        except Exception as e:
            print(f"Error in process_message: {e}")
            return {
                "response": "I apologize, but I encountered an error while processing your request. Please try again or rephrase your question.",
                "properties": None,
                "suggestions": ["Search for properties in a specific city", "Ask about market trends", "Get help with buying process"],
                "session_id": session_id,
                "requires_action": False,
                "action_type": None
            }

    def _store_chat_history(self, session_id: str, role: str, content: str):
        """Append message to chat history"""
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        self.conversation_history[session_id].append({
            "role": role,
            "content": content
        })

    async def _extract_search_criteria(self, message: str) -> Dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": PROPERTY_SEARCH_PROMPT.format(message=message)},
                    {"role": "user", "content": message}
                ],
                temperature=0.1,
                max_tokens=500
            )
            criteria_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', criteria_text, re.DOTALL)
            if json_match:
                criteria = json.loads(json_match.group())
                return criteria
            return {}
        except Exception as e:
            print(f"Error extracting search criteria: {e}")
            return {}

    async def _search_properties(self, criteria: Dict[str, Any]) -> List[Property]:
        try:
            filters = PropertySearchFilters(
                location=criteria.get('location'),
                min_price=criteria.get('min_price'),
                max_price=criteria.get('max_price'),
                bedrooms=criteria.get('bedrooms'),
                bathrooms=criteria.get('bathrooms'),
                property_type=criteria.get('property_type'),
                min_sqft=criteria.get('min_sqft'),
                max_sqft=criteria.get('max_sqft')
            )
            search_request = PropertySearchRequest(
                filters=filters,
                limit=10,
                sort_by="price",
                sort_order="asc"
            )
            search_response = search_engine.search_properties(search_request)
            return search_response.properties
        except Exception as e:
            print(f"Error searching properties: {e}")
            return []

    async def _generate_response(self, message: str, context: Optional[Dict[str, Any]], properties: List[Property]) -> str:
        try:
            context_str = json.dumps(context) if context else "No previous context"
            property_context = ""
            if properties:
                property_context = "\n\nFound Properties:\n"
                for i, prop in enumerate(properties[:3], 1):
                    property_context += f"{i}. {prop.title} - ${prop.price:,.0f} - {prop.location.city}, {prop.location.state}\n"
                    property_context += f"   {prop.details.bedrooms} bed, {prop.details.bathrooms} bath, {prop.details.square_feet} sqft\n"

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": REAL_ESTATE_AGENT_PROMPT.format(
                            context=context_str + property_context,
                            message=message
                        )
                    },
                    {"role": "user", "content": message}
                ],
                temperature=0.7,
                max_tokens=800
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I'm here to help you with your real estate needs. Could you please tell me what you're looking for?"

    async def _generate_suggestions(self, message: str, properties: List[Property]) -> List[str]:
        suggestions = []
        base_suggestions = [
            "Show me properties under $500,000",
            "Find 3-bedroom houses in Austin",
            "What's the market trend in this area?",
            "Compare neighborhoods for families"
        ]
        if properties:
            if len(properties) > 5:
                suggestions.append("Show me more properties like these")
            suggestions.append("Get detailed information about a specific property")
            suggestions.append("Compare these properties")
            locations = list(set([p.location.city for p in properties[:3]]))
            if locations:
                suggestions.append(f"Show market trends for {locations[0]}")
        while len(suggestions) < 4:
            for suggestion in base_suggestions:
                if suggestion not in suggestions:
                    suggestions.append(suggestion)
                    break
        return suggestions[:4]

    def get_property_recommendations(self, user_preferences: Dict[str, Any], available_properties: List[Property]) -> str:
        try:
            property_data = []
            for prop in available_properties[:10]:
                property_data.append({
                    "title": prop.title,
                    "price": prop.price,
                    "location": f"{prop.location.city}, {prop.location.state}",
                    "bedrooms": prop.details.bedrooms,
                    "bathrooms": prop.details.bathrooms,
                    "sqft": prop.details.square_feet,
                    "type": prop.details.property_type
                })
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": PROPERTY_RECOMMENDATION_PROMPT.format(
                            preferences=json.dumps(user_preferences),
                            properties=json.dumps(property_data)
                        )
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return "I can help you find the perfect property. Please tell me more about what you're looking for."

    def get_chat_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.conversation_history.get(session_id, [])[-limit:]

    def add_to_favorites(self, user_id: str, property_id: str) -> bool:
        if user_id not in self.user_favorites:
            self.user_favorites[user_id] = []
        if property_id not in self.user_favorites[user_id]:
            self.user_favorites[user_id].append(property_id)
        return True

    def remove_from_favorites(self, user_id: str, property_id: str) -> bool:
        if user_id in self.user_favorites and property_id in self.user_favorites[user_id]:
            self.user_favorites[user_id].remove(property_id)
        return True

    def get_user_favorites(self, user_id: str) -> List[str]:
        return self.user_favorites.get(user_id, [])

# Global agent instance
real_estate_agent = RealEstateAgent()
