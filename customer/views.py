import requests
from openai import OpenAI
from django.conf import settings
import base64
import json
client = OpenAI(api_key=settings.OPENAI_API_KEY)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChatSession, ChatMessage, Customer, QuestionAnswer
from datetime import date
from .sms import notify_vet
# @login_required
# def customer_dashboard(request):

#     session = (
#         ChatSession.objects
#         .filter(user=request.user)
#         .order_by("-updated_at")
#         .first()
#     )

#     if session:
#         return redirect("chat_session", session.id)

#     session = ChatSession.objects.create(
#         user=request.user,
#         title="New Chat"
#     )

#     return redirect("chat_session", session.id)
@login_required
def customer_dashboard(request):
    session = ChatSession.objects.create(
        user=request.user,
        title="New Chat"
    )

    return redirect("chat_session", session.id)

@login_required
def new_chat(request):
    session = ChatSession.objects.create(
        user=request.user,
        title="New Chat"
    )

    return redirect("chat_session", session_id=session.id)

@login_required
def chat_session(request, session_id):

    session = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    recent_chats = (
        ChatSession.objects
        .filter(user=request.user)
        .order_by("-updated_at")
    )

    return render(request, "pages/dashboard.html", {
        "session": session,
        "messages": session.messages.all(),
        "recent_chats": recent_chats,
    })

@login_required
@require_POST
def send_message(request, session_id):

    session = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    customer = get_object_or_404(
        Customer,
        user=request.user
    )

    # Calculate dog's age
    today = date.today()

    age = (
        today.year
        - customer.birthdate.year
        - (
            (today.month, today.day)
            <
            (customer.birthdate.month, customer.birthdate.day)
        )
    )

    user_message = request.POST.get("message", "").strip()
    image = request.FILES.get("image")

    ############################################################
    # SAVE USER MESSAGE
    ############################################################

    ChatMessage.objects.create(
        session=session,
        role="user",
        message=user_message if user_message else "[Image Uploaded]"
    )

    ############################################################
    # RENAME FIRST CHAT
    ############################################################

    if session.title == "New Chat":

        session.title = (
            user_message[:50]
            if user_message
            else "Dog Breed Analysis"
        )

        session.save()

    ############################################################
    # IMAGE ANALYSIS
    ############################################################

    if image:

        image_bytes = image.read()

        image_base64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are We Care Pet Care AI.

Analyze the uploaded dog image.

Return ONLY valid JSON.

{{
    "detected_breed":"Golden Retriever",
    "confidence":[
        {{
            "breed":"Golden Retriever",
            "percent":85
        }},
        {{
            "breed":"Labrador Retriever",
            "percent":10
        }},
        {{
            "breed":"Flat-Coated Retriever",
            "percent":5
        }}
    ],
    "description":"Brief breed description.",
    "comparison":"Compare with registered breed.",
    "registered":{{
        "name":"{customer.pet_name}",
        "breed":"{customer.breed}",
        "sex":"{customer.sex}",
        "age":{age}
    }}
}}

Rules

- Analyze dogs only.
- Confidence must total 100.
- If mixed breed estimate top 3.
- No markdown.
- JSON only.

If no dog detected:

{{
    "error":"No dog detected."
}}
"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_message or "Identify this dog's breed."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image.content_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]
        )

        ai_response = response.choices[0].message.content

        try:
            analysis = json.loads(ai_response)

        except Exception:

            analysis = {
                "error": "Unable to analyze image."
            }

        ChatMessage.objects.create(
            session=session,
            role="assistant",
            message=json.dumps(
                analysis,
                indent=4
            )
        )

        return JsonResponse({
            "success": True,
            "type": "image",
            "analysis": analysis
        })

    ############################################################
    # EMERGENCY DETECTION
    ############################################################

    emergency = client.chat.completions.create(
        model="gpt-4.1-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
Determine whether this dog owner's message describes a veterinary emergency.

Return JSON ONLY.

{
    "emergency": true,
    "reason":"Possible poisoning"
}

or

{
    "emergency": false,
    "reason":""
}

Emergency examples:

- poisoning
- vomiting blood
- severe bleeding
- seizure
- collapsed
- unconscious
- hit by car
- choking
- difficulty breathing
- heat stroke
- cannot stand
- emergency surgery
- bitten by snake

Only return TRUE when immediate veterinary care is recommended.
"""
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    try:

        emergency_result = json.loads(
            emergency.choices[0].message.content
        )

    except Exception:

        emergency_result = {
            "emergency": False,
            "reason": ""
        }

    ############################################################
    # SEND SMS TO VETERINARIAN
    ############################################################

    if emergency_result["emergency"]:

        try:

            notify_vet(
                customer,
                user_message,
                emergency_result['reason']
            )

        except Exception as e:

            print("SMS ERROR:", e)

    ############################################################
    # NORMAL CHAT
    ############################################################

    question = user_message.strip()

    qa = QuestionAnswer.objects.filter(
        question__iexact=question,
        is_active=True
    ).first()

    if qa:

        ChatMessage.objects.create(
            session=session,
            role="assistant",
            message=qa.answer
        )

        return JsonResponse({
            "success": True,
            "type": "chat",
            "response": qa.answer,
            "source": "knowledge_base",
            "emergency": emergency_result["emergency"],
            "reason": emergency_result["reason"]
        })

    messages = [
        {
            "role": "system",
            "content": f"""
You are We Care Pet Care AI.

Owner:
{customer.fullname}

Dog Name:
{customer.pet_name}

Breed:
{customer.breed}

Sex:
{customer.sex}

Age:
{age} years

Guidelines

- Answer only dog-related questions.
- Personalize replies using the dog's name.
- Never diagnose with certainty.
- Recommend visiting a veterinarian whenever symptoms are severe.
- If the situation appears life-threatening, strongly advise immediate veterinary care.
- Do not use Markdown.
"""
        }
    ]

    for msg in session.messages.all():

        messages.append({
            "role": msg.role,
            "content": msg.message
        })

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages
    )

    ai_response = response.choices[0].message.content

    ############################################################
    # LEARN NEW QUESTION & ANSWER
    ############################################################

    QuestionAnswer.objects.get_or_create(
        question=question,
        defaults={
            "answer": ai_response
        }
    )

    ############################################################
    # SAVE AI RESPONSE
    ############################################################

    ChatMessage.objects.create(
        session=session,
        role="assistant",
        message=ai_response
    )

    ############################################################
    # RETURN RESPONSE
    ############################################################

    return JsonResponse({
        "success": True,
        "type": "chat",
        "response": ai_response,
        "emergency": emergency_result["emergency"],
        "reason": emergency_result["reason"]
    })