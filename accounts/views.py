from django.utils import timezone

from django.contrib import messages
from django.shortcuts import render, redirect
from accounts.utils import create_default_admin
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from customer.models import Customer, Breed
from django.http import JsonResponse


User = get_user_model()

def keep_alive(request):
    return JsonResponse({
        "status": "ok",
        "service": "Django API",
        "timestamp": timezone.now().isoformat(),
    })

def login_view(request):
    create_default_admin()

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)

            if user.role == 'admin':
                return redirect('admin_dashboard')

            elif user.role == 'customer':
                return redirect('customer-dashboard')

            else:
                error = 'Your account does not have a valid role.'

        else:
            error = 'Incorrect username or password. Please try again.'

    return render(request, 'login.html', {
        'error': error,
    })

def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        form_data = {
            "username": username,
            "email": email,
        }

        # Validate required fields
        if not username or not email or not password:
            return render(request, "signup.html", {
                "error": "Please complete all required fields.",
                "form_data": form_data,
            })

        # Check duplicate username
        if User.objects.filter(username__iexact=username).exists():
            return render(request, "signup.html", {
                "error": "Username already exists. Please choose another.",
                "form_data": form_data,
            })

        # Check duplicate email
        if User.objects.filter(email__iexact=email).exists():
            return render(request, "signup.html", {
                "error": "Email already exists. Please use another email.",
                "form_data": form_data,
            })

        # Validate password length
        if len(password) < 8:
            return render(request, "signup.html", {
                "error": "Password must contain at least 8 characters.",
                "form_data": form_data,
            })

        # Create the account
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        # Log in the newly registered user
        login(request, user)

        return redirect("complete-profile")

    return render(request, "signup.html", {
        "form_data": {},
    })

@login_required
def complete_profile(request):
    if hasattr(request.user, "customer_profile"):
        return redirect("customer-dashboard")

    breeds = Breed.objects.filter(is_active=True).order_by("name")

    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        address = request.POST.get("address", "").strip()
        contact_number = request.POST.get("contact_number", "").strip()
        pet_name = request.POST.get("pet_name", "").strip()
        breed_id = request.POST.get("breed", "").strip()
        sex = request.POST.get("sex", "").strip()
        birthdate = request.POST.get("birthdate", "").strip()

        selected_breed = Breed.objects.filter(
            pk=breed_id,
            is_active=True
        ).first()

        if not all([
            fullname,
            address,
            contact_number,
            pet_name,
            selected_breed,
            sex in ("Male", "Female"),
            birthdate,
        ]):
            return render(request, "complete_profile.html", {
                "breeds": breeds,
                "error": "Please complete all fields and select a valid breed.",
                "form_data": request.POST,
            })

        try:
            Customer.objects.create(
                user=request.user,
                fullname=fullname,
                address=address,
                contact_number=contact_number,
                pet_name=pet_name,
                breed=selected_breed,
                sex=sex,
                birthdate=birthdate,
            )
        except Exception:
            return render(request, "complete_profile.html", {
                "breeds": breeds,
                "error": "We could not save your profile. Please try again.",
                "form_data": request.POST,
            })

        messages.success(request, "Your profile has been completed successfully.")
        return redirect("customer-dashboard")

    return render(request, "complete_profile.html", {
        "breeds": breeds,
        "form_data": {},
    })

def logout_view(request):
    logout(request)
    return redirect('login')