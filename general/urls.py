from django.urls import path

from general.views import PruebaView

urlpatterns = [
    path('prueba/', PruebaView.as_view()),
]
