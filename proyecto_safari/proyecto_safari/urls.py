from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('Safari.urls')),
]

# Manejadores globales de error HTTP para Django
handler404 = 'Safari.views.error_404_view'
handler500 = 'Safari.views.error_500_view'
handler403 = 'Safari.views.error_403_view'
handler400 = 'Safari.views.error_400_view'

