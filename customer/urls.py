from django.urls import path
from . import views

urlpatterns = [
    path('customer-dashboard/', views.customer_dashboard, name='customer-dashboard'),
    path("chat/new/", views.new_chat, name="new_chat"),
    path("chat/<int:session_id>/", views.chat_session, name="chat_session"),
    path("chat/<int:session_id>/send/", views.send_message, name="send_message"),
]
