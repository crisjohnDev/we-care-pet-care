from rest_framework import serializers
from django.contrib.auth import get_user_model
from customer.models import Customer
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['fullname', 'address', 'contact_number', 'pet_name', 'breed', 'sex', 'birthdate']