from django.urls import path
from .views import GlobalSearchAPIView, SuggestionsAPIView

urlpatterns = [
    path('api/search/', GlobalSearchAPIView.as_view(), name='global-search'),
    path('api/search/suggestions/', SuggestionsAPIView.as_view(), name='search-suggestions'),
]
