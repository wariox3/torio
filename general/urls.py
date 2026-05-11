from django.urls import path
from rest_framework.routers import DefaultRouter

from general.views import GenContactoViewSet, PruebaView

router = DefaultRouter()
router.register(r'contacto', GenContactoViewSet, basename='contacto')

urlpatterns = [
    path('prueba/', PruebaView.as_view()),
] + router.urls
