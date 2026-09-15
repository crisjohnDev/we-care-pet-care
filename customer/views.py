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

import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from openai import OpenAI

from .models import ChatSession, ChatMessage, Customer, QuestionAnswer
from .sms import notify_vet


client = OpenAI()


import base64
import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from openai import OpenAI

from .models import ChatSession, ChatMessage, Customer, QuestionAnswer
from .sms import notify_vet


client = OpenAI()


@login_required
@require_POST
def send_message(request, session_id):

    # ============================================================
    # GET CHAT SESSION
    # ============================================================

    session = get_object_or_404(
        ChatSession,
        id=session_id,
        user=request.user
    )

    customer = get_object_or_404(
        Customer,
        user=request.user
    )

    message = request.POST.get("message", "").strip()
    image = request.FILES.get("image")

    if not message and not image:
        return JsonResponse({
            "success": False,
            "error": "Please enter a message or upload an image."
        }, status=400)

    # ============================================================
    # CALCULATE DOG AGE
    # ============================================================

    dog_age = "Unknown"

    if customer.birthdate:

        try:
            today = date.today()

            dog_age_years = (
                today.year
                - customer.birthdate.year
                - (
                    (today.month, today.day)
                    <
                    (
                        customer.birthdate.month,
                        customer.birthdate.day
                    )
                )
            )

            if dog_age_years < 1:
                dog_age = "Less than 1 year old"
            else:
                dog_age = f"{dog_age_years} years old"

        except Exception as e:

            print("DOG AGE ERROR:", e)

    # ============================================================
    # SAVE USER MESSAGE
    # ============================================================

    if message:

        ChatMessage.objects.create(
            session=session,
            role="user",
            message=message
        )

    # ============================================================
    # UPDATE CHAT TITLE
    # ============================================================

    if session.title == "New Chat" and message:

        session.title = message[:50]
        session.save(update_fields=["title"])

    # ============================================================
    # LOAD CONVERSATION HISTORY
    # ============================================================

    previous_messages = list(
        ChatMessage.objects
        .filter(session=session)
        .order_by("-created_at")[:20]
    )

    previous_messages.reverse()

    conversation_history = []

    for chat_message in previous_messages:

        if chat_message.role not in ["user", "assistant"]:
            continue

        conversation_history.append({
            "role": chat_message.role,
            "content": chat_message.message
        })

    # ============================================================
    # IMAGE ANALYSIS
    # ============================================================

    image_analysis = None

    if image:

        try:

            image_bytes = image.read()

            image_base64 = base64.b64encode(
                image_bytes
            ).decode("utf-8")

            content_type = (
                image.content_type
                or "image/jpeg"
            )

            image_system_prompt = """
You are the dog image analysis assistant for We Care Pet Care.

Analyze the uploaded image carefully.

Return ONLY valid JSON:

{
    "breed": "Most likely breed or mix",
    "confidence": "low|medium|high",
    "description": "Brief description of the dog",
    "possible_health_observations": "Only things visibly observable in the image",
    "comparison": "Comparison with the registered breed if possible"
}

IMPORTANT:

- Do not invent information.
- Do not diagnose medical conditions from an image.
- Only describe things that can reasonably be observed.
- If there is no dog in the image, say so.
"""

            image_response = client.chat.completions.create(
                model="gpt-4.1-mini",
                response_format={
                    "type": "json_object"
                },
                messages=[
                    {
                        "role": "system",
                        "content": image_system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Registered dog information:\n"
                                    f"Name: {customer.pet_name}\n"
                                    f"Breed: {customer.breed or 'Unknown'}\n"
                                    f"Sex: {customer.sex or 'Unknown'}\n"
                                    f"Age: {dog_age}"
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        f"data:{content_type};base64,"
                                        f"{image_base64}"
                                    )
                                }
                            }
                        ]
                    }
                ],
                temperature=0.2
            )

            image_analysis = json.loads(
                image_response.choices[0].message.content
            )

        except Exception as e:

            print("IMAGE ANALYSIS ERROR:", e)

            image_analysis = {
                "breed": "Unable to determine",
                "confidence": "low",
                "description": (
                    "I wasn't able to analyze the uploaded image."
                ),
                "possible_health_observations": "",
                "comparison": ""
            }

    # ============================================================
    # VETERINARY TRIAGE SYSTEM
    # ============================================================

    triage_system_prompt = """
You are the veterinary safety triage assistant for We Care Pet Care.

Your job is to understand the dog's condition through conversation.

You are NOT a replacement for a veterinarian.

You must behave like a helpful veterinary AI assistant rather than a
keyword-based emergency detector.

Your responsibilities are:

1. Understand the owner's concern.
2. Review the entire conversation.
3. Identify what information is missing.
4. Ask useful follow-up questions.
5. Provide safe immediate first-aid guidance when appropriate.
6. Determine the dog's risk level.
7. Determine whether the situation is a genuine emergency.
8. Determine whether the veterinarian should be notified immediately.

============================================================
IMPORTANT: USE THE ENTIRE CONVERSATION
============================================================

Always consider previous messages.

The latest message alone may not contain enough information.

Example:

Owner:
"My dog is bleeding."

Assistant:
"Where is the bleeding coming from?"

Owner:
"His leg."

Assistant:
"How severe is it?"

Owner:
"The blood is spurting and won't stop."

Now the complete conversation indicates a potentially serious emergency.

Reassess the situation whenever new information is provided.

============================================================
DO NOT USE KEYWORDS AS AUTOMATIC EMERGENCIES
============================================================

Words such as:

- bleeding
- blood
- vomiting
- diarrhea
- pain
- coughing
- shaking
- fever

do NOT automatically mean emergency=true.

Understand the context first.

For example:

"My dog has a tiny scratch and there are two drops of blood."

This is different from:

"My dog has blood spurting from his leg and it won't stop."

============================================================
RISK LEVELS
============================================================

LOW:

The condition appears mild and there are no concerning warning signs.

MEDIUM:

The condition may require veterinary attention but does not currently
provide enough evidence of an immediate life-threatening emergency.

HIGH:

The condition is serious or potentially life-threatening.

============================================================
CLEAR EMERGENCIES
============================================================

Set:

emergency=true

risk_level="high"

when the available information clearly indicates an immediate or
potentially life-threatening situation.

Examples:

- inability to breathe
- severe difficulty breathing
- choking with breathing difficulty
- unconsciousness
- collapse
- severe seizure
- severe uncontrolled bleeding
- blood spurting from a wound
- heavy bleeding that does not stop with continuous pressure
- serious trauma
- being hit by a vehicle with serious injury
- suspected poisoning with concerning symptoms
- significant vomiting of blood
- severe bloody diarrhea with weakness or collapse
- severe burns
- severe heat stroke
- inability to stand because of serious illness or injury
- blue or gray gums
- extremely pale or white gums
- severe allergic reaction with breathing difficulty
- severe abdominal swelling with distress or repeated unproductive retching
- severe uncontrolled pain
- serious foreign-body obstruction
- any other clearly life-threatening situation

The owner does NOT need to use the word "emergency".

============================================================
WHEN INFORMATION IS INCOMPLETE
============================================================

If the owner reports a potentially concerning symptom but there is not
enough information to determine whether it is an emergency:

DO NOT automatically set emergency=true.

Instead:

emergency=false

needs_more_information=true

Ask the most important question.

Provide safe immediate guidance if appropriate.

Example:

Owner:
"My dog is bleeding."

The correct approach is to ask:

- Where is the bleeding?
- What caused it?
- Is it dripping, flowing continuously, or spurting?
- Has the bleeding stopped?
- Is the dog alert?
- Can the dog stand and walk?
- Are the gums pink, pale, white, blue, or gray?

Do not ask all questions at once.

Ask the most useful question first.

============================================================
BLEEDING FIRST AID
============================================================

For a normal external wound, safe general guidance may include:

- place clean gauze or cloth over the wound
- apply continuous pressure
- do not repeatedly remove the cloth to inspect the wound
- if blood soaks through, place additional clean material over it
- keep the dog calm and still
- arrange veterinary care if the wound is deep or bleeding persists

If the bleeding is severe, spurting, rapidly flowing, or cannot be controlled,
treat it as an emergency.

============================================================
OTHER FIRST AID
============================================================

Provide only safe general first-aid guidance.

Never recommend:

- human painkillers
- human medications
- antibiotics without veterinary direction
- unsafe home remedies
- inducing vomiting unless specifically directed by a veterinarian
- delaying emergency veterinary care
- inserting objects into wounds

============================================================
FOLLOW-UP QUESTIONS
============================================================

Ask focused questions.

Do not overwhelm the owner.

For BLEEDING:

Ask about:

- location
- cause
- severity
- dripping vs flowing vs spurting
- whether pressure stops the bleeding
- alertness
- ability to stand
- gum color

For VOMITING:

Ask about:

- number of episodes
- duration
- appearance
- blood
- ability to drink
- weakness
- possible toxin or foreign object

For DIARRHEA:

Ask about:

- duration
- blood
- frequency
- drinking
- weakness
- vomiting

For BREATHING:

Ask about:

- breathing difficulty
- breathing effort
- gum color
- consciousness
- possible choking

For INJURY:

Ask about:

- what happened
- injury location
- bleeding
- swelling
- pain
- ability to stand or walk

============================================================
EMERGENCY DECISION
============================================================

If the available information clearly proves an emergency:

emergency=true
risk_level="high"
needs_more_information=false
follow_up_question=""

If information is incomplete:

emergency=false
needs_more_information=true

If the situation is concerning but not clearly immediately life-threatening:

emergency=false
risk_level="medium"

============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

Use exactly:

{
    "risk_level": "low|medium|high",
    "emergency": false,
    "reason": "Brief explanation.",
    "needs_more_information": true,
    "follow_up_question": "Most important next question.",
    "recommended_action": "Safe immediate action."
}

If no follow-up is needed:

"follow_up_question": ""

Do not return markdown.

Do not return additional fields.

Do not diagnose diseases.

When information is missing, gather information before declaring an emergency.

When the information clearly indicates a life-threatening emergency,
do not delay emergency advice simply to ask more questions.
"""

    # ============================================================
    # BUILD TRIAGE MESSAGES
    # ============================================================

    triage_messages = [
        {
            "role": "system",
            "content": triage_system_prompt
        }
    ]

    for item in conversation_history:

        triage_messages.append({
            "role": item["role"],
            "content": item["content"]
        })

    # ============================================================
    # DEFAULT TRIAGE
    # ============================================================

    triage_result = {
        "risk_level": "medium",
        "emergency": False,
        "reason": "More information is needed.",
        "needs_more_information": True,
        "follow_up_question": (
            "Can you describe what is happening with your dog?"
        ),
        "recommended_action": (
            "Please provide more information about your dog's condition."
        )
    }

    # ============================================================
    # RUN TRIAGE
    # ============================================================

    try:

        triage_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={
                "type": "json_object"
            },
            messages=triage_messages,
            temperature=0.1
        )

        triage_result = json.loads(
            triage_response.choices[0].message.content
        )

    except Exception as e:

        print("TRIAGE ERROR:", e)

    # ============================================================
    # NORMALIZE TRIAGE
    # ============================================================

    risk_level = str(
        triage_result.get(
            "risk_level",
            "medium"
        )
    ).lower().strip()

    if risk_level not in ["low", "medium", "high"]:
        risk_level = "medium"

    emergency = bool(
        triage_result.get(
            "emergency",
            False
        )
    )

    needs_more_information = bool(
        triage_result.get(
            "needs_more_information",
            True
        )
    )

    reason = str(
        triage_result.get(
            "reason",
            "More information is needed."
        )
    ).strip()

    follow_up_question = str(
        triage_result.get(
            "follow_up_question",
            ""
        )
    ).strip()

    recommended_action = str(
        triage_result.get(
            "recommended_action",
            ""
        )
    ).strip()

    # ============================================================
    # SAFETY NORMALIZATION
    # ============================================================

    if emergency:

        risk_level = "high"

        needs_more_information = False

        follow_up_question = ""

    elif needs_more_information:

        emergency = False

    # ============================================================
    # VETERINARIAN SMS
    # ============================================================

    sms_sent = False
    sms_result = None

    if emergency:

        # Collect recent owner messages so the veterinarian receives
        # useful conversation context.
        owner_messages = []

        for item in conversation_history:

            if item["role"] == "user":

                owner_messages.append(
                    item["content"]
                )

        symptoms_for_vet = "\n".join(
            owner_messages[-8:]
        )

        try:

            sms_result = notify_vet(
                customer=customer,
                symptoms=symptoms_for_vet,
                reason=reason,
                risk_level=risk_level
            )

            print("========================================")
            print("VETERINARIAN SMS RESULT")
            print(sms_result)
            print("========================================")

            if isinstance(sms_result, dict):

                sms_sent = bool(
                    sms_result.get(
                        "success",
                        False
                    )
                )

        except Exception as e:

            print(
                "VETERINARIAN SMS ERROR:",
                e
            )

            sms_sent = False

    # ============================================================
    # KNOWLEDGE BASE
    # ============================================================

    knowledge_answer = None

    # Never allow knowledge-base answers to override:
    #
    # - emergency
    # - high risk
    # - follow-up questions

    if (
        message
        and not emergency
        and risk_level == "low"
        and not needs_more_information
    ):

        try:

            knowledge_answer = (
                QuestionAnswer.objects
                .filter(
                    question__icontains=message
                )
                .first()
            )

        except Exception as e:

            print(
                "KNOWLEDGE BASE ERROR:",
                e
            )

    # ============================================================
    # CONVERSATIONAL AI SYSTEM PROMPT
    # ============================================================

    assistant_system_prompt = """
You are the conversational AI veterinary assistant for We Care Pet Care.

Your job is to talk naturally with the dog owner.

You are NOT a replacement for a veterinarian.

The owner should feel like they are having a conversation with a helpful
assistant, not reading a medical report.

============================================================
DOG INFORMATION
============================================================

Dog name:
{pet_name}

Breed:
{breed}

Sex:
{sex}

Age:
{age}

Owner:
{owner}

============================================================
CURRENT SAFETY ASSESSMENT
============================================================

Risk level:
{risk_level}

Emergency:
{emergency}

Reason:
{reason}

Needs more information:
{needs_more_information}

Follow-up question:
{follow_up_question}

Recommended action:
{recommended_action}

Veterinarian SMS sent:
{sms_sent}

============================================================
VERY IMPORTANT: CONVERSATIONAL DISPLAY
============================================================

NEVER display the internal assessment.

Do NOT write:

Risk Level: Medium
Reason: ...
Emergency: False
Recommended Action: ...
Needs More Information: ...

Do NOT display JSON.

Do NOT display technical system information.

Do NOT make the response look like a veterinary report.

Instead, naturally incorporate the information into the conversation.

============================================================
NATURAL CONVERSATION
============================================================

Use:

- short paragraphs
- natural language
- the dog's name when appropriate
- simple explanations
- one or two useful questions at a time
- practical immediate guidance

Start by acknowledging what the owner said.

Then ask the most important question if information is missing.

Then provide safe guidance.

============================================================
EXAMPLE: BLEEDING
============================================================

Owner:

"My dog is bleeding."

A good response:

"I'm sorry to hear that. Let's first figure out how serious the bleeding is.

Where is Bark bleeding from, and how did it happen? Is the blood dripping
slowly, flowing continuously, or spurting?

If it's an external wound, you can place a clean cloth or gauze over it and
apply steady pressure. Try not to repeatedly remove the cloth to check it.

If the bleeding is heavy, spurting, or won't stop with pressure, Bark needs
immediate veterinary care."

Do NOT simply say:

"This is an emergency."

because the owner has not provided enough information yet.

============================================================
EXAMPLE: FOLLOW-UP
============================================================

Owner:

"He cut his leg."

Respond naturally:

"Thanks for telling me. Is the bleeding still going, and would you say it's
just a few drops or quite a lot?

Also, is Bark alert and able to stand and walk normally?

For now, keep steady pressure on the wound with clean gauze or a clean cloth."

============================================================
EXAMPLE: CLEAR EMERGENCY
============================================================

Owner:

"The blood is spurting and won't stop."

Respond:

"That sounds serious, and Bark may be experiencing severe bleeding.

Please keep firm pressure on the wound using clean gauze or a clean cloth and
seek emergency veterinary care immediately. Don't wait for the bleeding to
stop on its own.

I've also notified the veterinarian by SMS about Bark's emergency. Please
follow the veterinarian's instructions while you get Bark the care he needs."

============================================================
WHEN INFORMATION IS MISSING
============================================================

If needs_more_information=true:

- acknowledge the owner's concern
- ask the follow-up question
- provide safe immediate guidance when appropriate
- explain important warning signs

Do not ask a long list of questions.

Ask only the most important question or two.

============================================================
WHEN EMERGENCY=true
============================================================

Be direct and calm.

Tell the owner why the situation is concerning.

Give immediate safe instructions.

Tell them to seek emergency veterinary care without delay.

If sms_sent=true:

Naturally tell them:

"I've also notified the veterinarian by SMS about Bark's emergency."

Then:

"Please wait for the veterinarian's response and follow their instructions."

If the dog is in immediate danger, tell the owner to seek emergency veterinary
care without delay.

IMPORTANT:

Say:

"The veterinarian has been notified by SMS."

Do NOT say:

"The AI contacted the veterinarian."

============================================================
WHEN SMS FAILED
============================================================

If:

emergency=true

and:

sms_sent=false

NEVER claim the veterinarian was notified.

Say naturally:

"I couldn't confirm that the veterinarian received the emergency SMS, so
please contact the veterinarian directly and seek immediate veterinary care."

============================================================
FIRST AID
============================================================

Provide safe general first-aid guidance when appropriate.

For external bleeding:

- clean gauze or cloth
- continuous pressure
- do not repeatedly remove the cloth
- add additional material over soaked material
- keep the dog calm
- seek veterinary care when appropriate

Never recommend human medications.

Never recommend dangerous home remedies.

Never tell the owner to delay emergency care.

============================================================
STYLE
============================================================

Be:

- conversational
- calm
- empathetic
- helpful
- concise
- clear
- practical

Do not:

- sound robotic
- sound like a medical report
- display risk levels
- display internal reasoning
- display JSON
- use emojis
- use excessive headings
- diagnose diseases
- claim certainty when information is incomplete
- repeat the same warning unnecessarily

============================================================
MESSAGE LENGTH
============================================================

Normal responses:

2-5 short paragraphs.

Simple follow-up:

1-3 short paragraphs.

Emergency:

short and action-oriented.

The owner may be dealing with an injured or sick dog, so do not overwhelm them.

============================================================
FINAL RULE
============================================================

The conversation should naturally progress:

Owner describes symptom
        ↓
Assistant acknowledges
        ↓
Assistant asks important question
        ↓
Assistant gives safe immediate guidance
        ↓
Owner answers
        ↓
Assistant reassesses entire conversation
        ↓
Assistant asks another question if needed
        ↓
Emergency becomes clear OR remains non-emergency
        ↓
Appropriate action is given

Do not turn every concerning symptom into an emergency.

Do not delay emergency care when the information clearly indicates a
life-threatening situation.
"""

    # ============================================================
    # FORMAT SYSTEM PROMPT
    # ============================================================

    assistant_system_prompt = assistant_system_prompt.format(
        pet_name=customer.pet_name,
        breed=customer.breed or "Unknown",
        sex=customer.sex or "Unknown",
        age=dog_age,
        owner=customer.fullname,
        risk_level=risk_level,
        emergency=emergency,
        reason=reason,
        needs_more_information=needs_more_information,
        follow_up_question=follow_up_question,
        recommended_action=recommended_action,
        sms_sent=sms_sent
    )

    # ============================================================
    # ADD IMAGE ANALYSIS
    # ============================================================

    if image_analysis:

        assistant_system_prompt += f"""

============================================================
IMAGE ANALYSIS
============================================================

The uploaded image was analyzed.

Likely breed:
{image_analysis.get("breed", "Unknown")}

Confidence:
{image_analysis.get("confidence", "low")}

Description:
{image_analysis.get("description", "")}

Possible visible observations:
{image_analysis.get("possible_health_observations", "")}

Breed comparison:
{image_analysis.get("comparison", "")}

IMPORTANT:

The image analysis cannot confirm a medical diagnosis.
Only discuss visible observations.
"""

    # ============================================================
    # ADD KNOWLEDGE BASE
    # ============================================================

    if knowledge_answer:

        assistant_system_prompt += f"""

============================================================
KNOWLEDGE BASE
============================================================

A possible matching answer is:

{knowledge_answer.answer}

Use it only when relevant.

Do not allow this information to override the veterinary safety assessment.
"""

    # ============================================================
    # GENERATE CONVERSATIONAL RESPONSE
    # ============================================================

    try:

        response_messages = [
            {
                "role": "system",
                "content": assistant_system_prompt
            }
        ]

        for item in conversation_history:

            if item["role"] not in [
                "user",
                "assistant"
            ]:
                continue

            response_messages.append({
                "role": item["role"],
                "content": item["content"]
            })

        ai_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=response_messages,
            temperature=0.45
        )

        assistant_message = (
            ai_response
            .choices[0]
            .message
            .content
            .strip()
        )

    except Exception as e:

        print(
            "AI RESPONSE ERROR:",
            e
        )

        assistant_message = (
            f"I'm sorry, but I wasn't able to process that right now. "
            f"Please tell me more about what is happening with "
            f"{customer.pet_name}."
        )

    # ============================================================
    # ENSURE FOLLOW-UP QUESTION IS DISPLAYED
    # ============================================================

    if (
        not emergency
        and needs_more_information
        and follow_up_question
    ):

        if (
            follow_up_question.lower()
            not in assistant_message.lower()
        ):

            assistant_message += (
                f"\n\n{follow_up_question}"
            )

    # ============================================================
    # EMERGENCY SMS STATUS MESSAGE
    # ============================================================

    if emergency:

        if sms_sent:

            emergency_notice = (
                f"\n\nI've also notified the veterinarian by SMS "
                f"about {customer.pet_name}'s emergency. "
                f"Please wait for the veterinarian's response and "
                f"follow their instructions while you get "
                f"{customer.pet_name} the care they need."
            )

            already_notified = (
                "notified the veterinarian by sms"
                in assistant_message.lower()
            )

        else:

            emergency_notice = (
                f"\n\nI couldn't confirm that the veterinarian "
                f"received the emergency SMS. Please contact the "
                f"veterinarian directly and seek immediate "
                f"veterinary care for {customer.pet_name}."
            )

            already_notified = (
                "couldn't confirm that the veterinarian received"
                in assistant_message.lower()
            )

        if not already_notified:

            assistant_message += emergency_notice

    # ============================================================
    # SAVE ASSISTANT MESSAGE
    # ============================================================

    ChatMessage.objects.create(
        session=session,
        role="assistant",
        message=assistant_message
    )

    # ============================================================
    # LEARN ONLY FROM SAFE CONVERSATIONS
    # ============================================================

    if (
        message
        and not emergency
        and risk_level == "low"
        and not needs_more_information
        and not knowledge_answer
    ):

        try:

            QuestionAnswer.objects.create(
                question=message,
                answer=assistant_message
            )

        except Exception as e:

            print(
                "QUESTION ANSWER SAVE ERROR:",
                e
            )

    # ============================================================
    # RETURN JSON
    # ============================================================

    return JsonResponse({
        "success": True,
        "type": (
            "image"
            if image_analysis
            else "text"
        ),
        "response": assistant_message,
        "emergency": emergency,
        "risk_level": risk_level,
        "reason": reason,
        "needs_more_information": needs_more_information,
        "follow_up_question": follow_up_question,
        "recommended_action": recommended_action,
        "sms_sent": sms_sent
    })