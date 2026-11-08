import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from django.db.models.functions import (
    TruncDate,
    TruncWeek,
    TruncMonth,
    TruncYear,
)

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from customer.models import Breed, Customer, Dog, ChatSession, ChatMessage, QuestionAnswer
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Q


@login_required
def core_dashboard(request):
    breeds = Breed.objects.all().count()
    customers = Customer.objects.all().count()
    dogs = Dog.objects.all().count()
    chat_sessions = ChatSession.objects.all().count()
    chat_messages = ChatMessage.objects.all().count()
    question_answer = QuestionAnswer.objects.all().count()

    context = {
        'breeds': breeds,
        'customers': customers,
        'dogs': dogs,
        'chat_sessions': chat_sessions,
        'chat_messages': chat_messages,
        'question_answer': question_answer,
    }
    return render(request, 'core/core_dashboard.html', context)


@login_required
def dog_breed_list(request):
    breeds = Breed.objects.all()

    return render(request, 'core/dog_list.html', {
        'breeds': breeds
    })


@login_required
def dog_breed_edit(request, pk):
    breed = get_object_or_404(Breed, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, 'Breed name is required.')
        elif Breed.objects.filter(name__iexact=name).exclude(pk=breed.pk).exists():
            messages.error(request, 'This breed already exists.')
        else:
            breed.name = name
            breed.description = description
            breed.is_active = is_active
            breed.save()

            messages.success(request, 'Breed updated successfully.')
            return redirect('dog_breed_list')

    return render(request, 'core/dog_breed_edit.html', {
        'breed': breed
    })


@login_required
def dog_breed_delete(request, pk):
    breed = get_object_or_404(Breed, pk=pk)

    if request.method == 'POST':
        breed_name = breed.name
        breed.delete()

        messages.success(
            request,
            f'{breed_name} has been deleted successfully.'
        )

    return redirect('dog_breed_list')

@login_required
def customer_list(request):
    customers = Customer.objects.annotate(
        dog_count=Count('dogs', distinct=True),
        chat_count=Count('user__chat_sessions', distinct=True)
    ).order_by('-created_at')

    search = request.GET.get('search', '').strip()

    if search:
        customers = customers.filter(
            Q(fullname__icontains=search) |
            Q(contact_number__icontains=search) |
            Q(address__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search)
        )

    return render(request, 'core/customer_list.html', {
        'customers': customers,
        'search': search,
    })


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(
        Customer.objects.select_related('user'),
        pk=pk
    )

    dogs = customer.dogs.select_related('breed').order_by('-created_at')

    chat_sessions = customer.user.chat_sessions.annotate(
        message_count=Count('messages')
    ).order_by('-updated_at')

    return render(request, 'core/customer_detail.html', {
        'customer': customer,
        'dogs': dogs,
        'chat_sessions': chat_sessions,
    })


@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == 'POST':
        customer_name = customer.fullname

        # Customer.user is OneToOneField with CASCADE.
        # Deleting the user also deletes their related chat sessions.
        customer.user.delete()

        messages.success(
            request,
            f'{customer_name} and their associated records have been deleted.'
        )

        return redirect('customer_list')

    return redirect('customer_detail', pk=pk)


@login_required
def chat_session_list(request):
    sessions = ChatSession.objects.select_related(
        'user',
        'user__customer_profile'
    ).annotate(
        message_count=Count('messages')
    ).order_by('-updated_at')

    search = request.GET.get('search', '').strip()

    if search:
        sessions = sessions.filter(
            Q(title__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__customer_profile__fullname__icontains=search)
        )

    return render(request, 'core/chat_session_list.html', {
        'sessions': sessions,
        'search': search,
    })


@login_required
def chat_session_detail(request, pk):
    session = get_object_or_404(
        ChatSession.objects.select_related(
            'user',
            'user__customer_profile'
        ),
        pk=pk
    )

    chat_messages = session.messages.all()

    return render(request, 'core/chat_session_detail.html', {
        'session': session,
        'chat_messages': chat_messages,
    })


@login_required
def question_answer_list(request):
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()

    questions = QuestionAnswer.objects.all()

    if search:
        questions = questions.filter(
            Q(question__icontains=search) |
            Q(answer__icontains=search)
        )

    if status == "active":
        questions = questions.filter(is_active=True)
    elif status == "inactive":
        questions = questions.filter(is_active=False)

    context = {
        "questions": questions,
        "search": search,
        "status": status,
        "total_count": QuestionAnswer.objects.count(),
        "active_count": QuestionAnswer.objects.filter(is_active=True).count(),
        "inactive_count": QuestionAnswer.objects.filter(is_active=False).count(),
    }

    return render(request, "core/question_answer_list.html", context)


@login_required
def question_answer_create(request):
    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        answer = request.POST.get("answer", "").strip()
        is_active = request.POST.get("is_active") == "on"

        if not question or not answer:
            messages.error(request, "Question and answer are required.")
            return render(request, "core/question_answer_form.html", {
                "page_title": "Add Question & Answer",
                "question": question,
                "answer": answer,
                "is_active": is_active,
            })

        if QuestionAnswer.objects.filter(question__iexact=question).exists():
            messages.error(request, "This question already exists.")
            return render(request, "core/question_answer_form.html", {
                "page_title": "Add Question & Answer",
                "question": question,
                "answer": answer,
                "is_active": is_active,
            })

        QuestionAnswer.objects.create(
            question=question,
            answer=answer,
            is_active=is_active,
        )

        messages.success(request, "Question and answer added successfully.")
        return redirect("question_answer_list")

    return render(request, "core/question_answer_form.html", {
        "page_title": "Add Question & Answer",
        "is_active": True,
    })


@login_required
def question_answer_edit(request, pk):
    item = get_object_or_404(QuestionAnswer, pk=pk)

    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        answer = request.POST.get("answer", "").strip()
        is_active = request.POST.get("is_active") == "on"

        if not question or not answer:
            messages.error(request, "Question and answer are required.")
        elif QuestionAnswer.objects.filter(
            question__iexact=question
        ).exclude(pk=item.pk).exists():
            messages.error(request, "Another entry already uses this question.")
        else:
            item.question = question
            item.answer = answer
            item.is_active = is_active
            item.save()

            messages.success(request, "Question and answer updated successfully.")
            return redirect("question_answer_list")

        return render(request, "core/question_answer_form.html", {
            "page_title": "Edit Question & Answer",
            "item": item,
            "question": question,
            "answer": answer,
            "is_active": is_active,
        })

    return render(request, "core/question_answer_form.html", {
        "page_title": "Edit Question & Answer",
        "item": item,
        "question": item.question,
        "answer": item.answer,
        "is_active": item.is_active,
    })


@login_required
def question_answer_toggle(request, pk):
    item = get_object_or_404(QuestionAnswer, pk=pk)

    if request.method == "POST":
        item.is_active = not item.is_active
        item.save(update_fields=["is_active", "updated_at"])

        state = "activated" if item.is_active else "deactivated"
        messages.success(request, f"Question and answer {state} successfully.")

    return redirect("question_answer_list")


@login_required
def question_answer_delete(request, pk):
    item = get_object_or_404(QuestionAnswer, pk=pk)

    if request.method == "POST":
        item.delete()
        messages.success(request, "Question and answer deleted successfully.")

    return redirect("question_answer_list")

@login_required
def reports_dashboard(request):
    period = request.GET.get("period", "daily")

    if period not in ["daily", "weekly", "monthly", "yearly"]:
        period = "daily"

    today = timezone.localdate()

    # -----------------------------------
    # GENERATE REPORTING DATE RANGES
    # -----------------------------------

    buckets = []

    if period == "daily":
        start_date = today - timedelta(days=6)

        for i in range(7):
            buckets.append(start_date + timedelta(days=i))

        end_date = today + timedelta(days=1)
        trunc_function = TruncDate
        date_format = "%b %d"

    elif period == "weekly":
        current_week = today - timedelta(days=today.weekday())
        start_date = current_week - timedelta(weeks=7)

        for i in range(8):
            buckets.append(start_date + timedelta(weeks=i))

        end_date = current_week + timedelta(weeks=1)
        trunc_function = TruncWeek
        date_format = "Week of %b %d"

    elif period == "monthly":
        current_month = today.replace(day=1)

        for i in range(11, -1, -1):
            month_index = current_month.month - 1 - i
            year = current_month.year + month_index // 12
            month = month_index % 12 + 1
            buckets.append(date(year, month, 1))

        start_date = buckets[0]

        next_month_index = current_month.month
        end_year = current_month.year + next_month_index // 12
        end_month = next_month_index % 12 + 1
        end_date = date(end_year, end_month, 1)

        trunc_function = TruncMonth
        date_format = "%b %Y"

    else:
        start_date = date(today.year - 4, 1, 1)

        for i in range(5):
            buckets.append(date(today.year - 4 + i, 1, 1))

        end_date = date(today.year + 1, 1, 1)
        trunc_function = TruncYear
        date_format = "%Y"

    # -----------------------------------
    # CONVERT DATE RANGE TO DATETIME
    # -----------------------------------

    start_datetime = timezone.make_aware(
        datetime.combine(start_date, time.min)
    )

    end_datetime = timezone.make_aware(
        datetime.combine(end_date, time.min)
    )

    # -----------------------------------
    # AGGREGATE DATA
    # -----------------------------------

    def get_report_data(model):
        records = (
            model.objects
            .filter(
                created_at__gte=start_datetime,
                created_at__lt=end_datetime
            )
            .annotate(
                report_date=trunc_function("created_at")
            )
            .values("report_date")
            .annotate(total=Count("id"))
        )

        results = {}

        for record in records:
            report_date = record["report_date"]

            if isinstance(report_date, datetime):
                report_date = report_date.date()

            if period == "weekly":
                report_date = report_date - timedelta(
                    days=report_date.weekday()
                )

            elif period == "monthly":
                report_date = report_date.replace(day=1)

            elif period == "yearly":
                report_date = report_date.replace(month=1, day=1)

            results[report_date] = record["total"]

        return [results.get(bucket, 0) for bucket in buckets]

    customer_data = get_report_data(Customer)
    pet_data = get_report_data(Dog)
    session_data = get_report_data(ChatSession)
    message_data = get_report_data(ChatMessage)

    # -----------------------------------
    # CHART LABELS
    # -----------------------------------

    labels = []

    for bucket in buckets:
        if period == "weekly":
            labels.append("Week of " + bucket.strftime("%b %d"))
        else:
            labels.append(bucket.strftime(date_format))

    # -----------------------------------
    # TOTALS FOR SELECTED PERIOD
    # -----------------------------------

    total_customers = sum(customer_data)
    total_pets = sum(pet_data)
    total_sessions = sum(session_data)
    total_messages = sum(message_data)

    chart_data = {
        "labels": labels,
        "customers": customer_data,
        "pets": pet_data,
        "sessions": session_data,
        "messages": message_data,
    }

    context = {
        "period": period,
        "chart_data": chart_data,
        "total_customers": total_customers,
        "total_pets": total_pets,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "report_start": start_date,
        "report_end": end_date - timedelta(days=1),
    }

    return render(
        request,
        "core/reports.html",
        context
    )