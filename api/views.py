
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer, CustomerSerializer


class CustomerTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        if self.user.role != "customer":
            raise AuthenticationFailed(
                "Access denied. Only customers are allowed to log in here.",
                code="authorization",
            )

        data["role"] = self.user.role
        data["username"] = self.user.username

        return data


class CustomerLoginView(TokenObtainPairView):
    serializer_class = CustomerTokenObtainPairSerializer


class CustomerRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the user with the customer role.
        user = serializer.save(role="customer")

        # Generate JWT tokens after registration.
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Customer registered successfully!",
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class CustomerProfileCreateView(generics.CreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
