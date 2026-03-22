from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from hotels.models import HotelDataModel
from restaurants.models import RestaurantDataModel
from hotels.serializers import HotelListSerializer
from restaurants.serializers import RestaurantSerializer
from .utils import haversine_distance

class GlobalSearchAPIView(APIView):
    def get(self, request):
        try:
            query = request.query_params.get('q', '')
            city_param = request.query_params.get('city', '')
            lat_str = request.query_params.get('lat')
            lng_str = request.query_params.get('lng')
            search_type = request.query_params.get('type', 'all')

            lat, lng = None, None
            if lat_str and lng_str:
                try:
                    lat = float(lat_str)
                    lng = float(lng_str)
                except (ValueError, TypeError):
                    pass

            # Basic NL processing: Strip 'near', 'nearby', 'around', 'me'
            processed_query = query.lower()
            nl_keywords = ['near', 'nearby', 'around', ' me', 'hotels', 'hotel', 'restaurants', 'restaurant']
            for kw in nl_keywords:
                processed_query = processed_query.replace(kw, '').strip()
            
            # If processed_query is empty, it was pure filler (e.g., "near me").
            # Return all results but prioritized by location.
            search_query = processed_query if processed_query else None

            results = []

            # 1. Search Hotels
            if search_type in ['all', 'hotel']:
                hotel_qs = HotelDataModel.objects.all()
                if search_query:
                    hotel_qs = hotel_qs.filter(
                        Q(name__icontains=search_query) |
                        Q(city__icontains=search_query) |
                        Q(area__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(amenities__icontains=search_query) |
                        Q(badge__icontains=search_query) |
                        Q(keywords__icontains=search_query)
                    )
                if city_param and city_param.lower() != "all" and city_param != "Current Location":
                    hotel_qs = hotel_qs.filter(city__iexact=city_param)
                
                hotel_data = HotelListSerializer(hotel_qs, many=True, context={'request': request}).data
                for item in hotel_data:
                    item['result_type'] = 'hotel'
                    if lat is not None and lng is not None and item.get('id'):
                        try:
                            hotel_obj = HotelDataModel.objects.get(id=item['id'])
                            if hotel_obj.latitude is not None and hotel_obj.longitude is not None:
                                item['distance'] = haversine_distance(
                                    lat, lng, 
                                    hotel_obj.latitude, hotel_obj.longitude
                                )
                            else:
                                item['distance'] = None
                        except Exception:
                            item['distance'] = None
                    results.append(item)

            # 2. Search Restaurants
            if search_type in ['all', 'restaurant']:
                rest_qs = RestaurantDataModel.objects.all()
                if search_query:
                    rest_qs = rest_qs.filter(
                        Q(name__icontains=search_query) |
                        Q(city__icontains=search_query) |
                        Q(area__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(cuisine_type__icontains=search_query) |
                        Q(badge__icontains=search_query) |
                        Q(keywords__icontains=search_query)
                    )
                if city_param and city_param.lower() != "all" and city_param != "Current Location":
                    rest_qs = rest_qs.filter(city__iexact=city_param)
                
                rest_data = RestaurantSerializer(rest_qs, many=True, context={'request': request}).data
                for item in rest_data:
                    item['result_type'] = 'restaurant'
                    if lat is not None and lng is not None and item.get('id'):
                        try:
                            rest_obj = RestaurantDataModel.objects.get(id=item['id'])
                            if rest_obj.latitude is not None and rest_obj.longitude is not None:
                                item['distance'] = haversine_distance(
                                    lat, lng, 
                                    rest_obj.latitude, rest_obj.longitude
                                )
                            else:
                                item['distance'] = None
                        except Exception:
                            item['distance'] = None
                    results.append(item)

            # 3. Sort by distance if applicable
            if lat is not None and lng is not None:
                results.sort(key=lambda x: x.get('distance') if x.get('distance') is not None else float('inf'))

            return Response(results, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SuggestionsAPIView(APIView):
    """
    Returns simple autocomplete suggestions based on query, including keywords
    """
    def get(self, request):
        query = request.query_params.get('q', '')
        if not query or len(query) < 2:
            return Response([], status=status.HTTP_200_OK)

        # Basic NL processing
        search_query = query.lower()
        for kw in ['near ', 'nearby ', 'around ', ' me', 'hotels', 'hotel', 'restaurants', 'restaurant']:
            search_query = search_query.replace(kw, '').strip()
        
        # If query is just "near me", we use "me"? No, better to fall back to original if empty or too short
        query = search_query if len(search_query) >= 2 else query

        suggestions = []
        added_labels = set()

        # 1. Keywords (Priority) - Scan both models
        # Use a more efficient way to collect unique keywords
        current_kw = set()
        
        # Hotel Keywords
        h_kw = HotelDataModel.objects.filter(keywords__icontains=query).values_list('keywords', flat=True).distinct()
        for k_str in h_kw:
            if k_str:
                for p in [k.strip() for k in k_str.split(',') if query.lower() in k.lower()]:
                    if p.lower() not in current_kw:
                        current_kw.add(p.lower())
                        suggestions.append({'label': f"✨ {p}", 'value': p, 'type': 'keyword'})
                        added_labels.add(p.lower())
                    if len(suggestions) > 10: break
            if len(suggestions) > 10: break

        # Restaurant Keywords
        r_kw = RestaurantDataModel.objects.filter(keywords__icontains=query).values_list('keywords', flat=True).distinct()
        for k_str in r_kw:
            if k_str:
                for p in [k.strip() for k in k_str.split(',') if query.lower() in k.lower()]:
                    if p.lower() not in current_kw:
                        current_kw.add(p.lower())
                        suggestions.append({'label': f"✨ {p}", 'value': p, 'type': 'keyword'})
                        added_labels.add(p.lower())
                    if len(suggestions) > 15: break
            if len(suggestions) > 15: break

        # 2. Hotel Names (limit to 3 if keywords already found)
        hotels = HotelDataModel.objects.filter(name__icontains=query)[:5]
        for h in hotels:
            if h.name.lower() not in added_labels:
                suggestions.append({'label': h.name, 'value': h.name, 'type': 'hotel'})
                added_labels.add(h.name.lower())
                if len(suggestions) > 20: break

        # 3. Restaurant Names
        restaurants = RestaurantDataModel.objects.filter(name__icontains=query)[:5]
        for r in restaurants:
            if r.name.lower() not in added_labels:
                suggestions.append({'label': r.name, 'value': r.name, 'type': 'restaurant'})
                added_labels.add(r.name.lower())
                if len(suggestions) > 25: break

        # 4. Cities
        cities = HotelDataModel.objects.filter(city__icontains=query).values_list('city', flat=True).distinct()[:3]
        for c in cities:
            if c.lower() not in added_labels:
                suggestions.append({'label': f"📍 {c}", 'value': c, 'type': 'city'})
                added_labels.add(c.lower())

        # 5. Cuisine Types
        cuisines = RestaurantDataModel.objects.filter(cuisine_type__icontains=query).values_list('cuisine_type', flat=True).distinct()[:3]
        for cui in cuisines:
            if cui.lower() not in added_labels:
                suggestions.append({'label': f"🍽️ {cui}", 'value': cui, 'type': 'cuisine'})
                added_labels.add(cui.lower())

        return Response(suggestions, status=status.HTTP_200_OK)
