from django.shortcuts import render, redirect
from accounts.utils import create_default_admin
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from customer.models import Customer

User = get_user_model()

def login_view(request):
    create_default_admin()

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.role == 'admin':
                return redirect('admin_dashboard')
            elif user.role == 'customer':
                return redirect('customer-dashboard')
            else:
                return redirect('login')

        return redirect('login')

    return render(request, 'login.html')

def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():
            return render(request, "signup.html", {
                "error": "Username already exists."
            })

        if User.objects.filter(email=email).exists():
            return render(request, "signup.html", {
                "error": "Email already exists."
            })

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        login(request, user)
        return redirect("complete-profile")

    return render(request, "signup.html")

@login_required
def complete_profile(request):
    if request.method == "POST":
        Customer.objects.create(
            user=request.user,
            fullname=request.POST.get("fullname"),
            address=request.POST.get("address"),
            contact_number=request.POST.get("contact_number"),
            pet_name=request.POST.get("pet_name"),
            breed=request.POST.get("breed"),
            sex=request.POST.get("sex"),
            birthdate=request.POST.get("birthdate")
        )

        return redirect("customer-dashboard")

    return render(request, "complete_profile.html")

def logout_view(request):
    logout(request)
    return redirect('login')