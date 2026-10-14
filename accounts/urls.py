from django.urls import path
from . import views

urlpatterns = [
    path("api/keep-alive/", views.keep_alive, name="keep_alive"),
    path('', views.login_view, name='login'),
    path('create-account/', views.signup_view, name='signup'),
    path('complete-profile/', views.complete_profile, name='complete-profile'),
    path('logout/', views.logout_view, name='logout')
]