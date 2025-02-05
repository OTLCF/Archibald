import os

import json

import re

from dotenv import load_dotenv

from dateutil.parser import parse

from datetime import datetime

from flask import Flask, request, jsonify, session

from flask_cors import CORS, cross_origin

from langdetect import detect

from translate import Translator

import openai



# Configuration OpenAI

# Load environment variables
load_dotenv()
secret_key = os.getenv('SECRET_KEY')
openai.api_key = secret_key

# Flask setup

app = Flask(__name__)

CORS(app, origins=["https://phareducapferret.com"], supports_credentials=True)

app.secret_key = "archi33950baldBOT"



def preprocess_knowledge(raw_knowledge):

    """

    Transforme et prétraite les données JSON pour structurer les informations en sections exploitables.

    """

    knowledge = {

        "questions_and_responses": [],

        "general_information": [],

        "schedule": [],

        "pricing": {},

        "faq": []

    }



    for section, items in raw_knowledge.items():

        if section == "schedule":

            # Traiter la section des horaires

            for schedule_item in items:

                if isinstance(schedule_item, dict):

                    knowledge["schedule"].append(schedule_item)

                else:

                    print(f"Unexpected item format in section '{section}': {schedule_item}")



        elif section == "pricing":

            # Traiter la section des tarifs

            if isinstance(items, dict):

                knowledge["pricing"] = items

            else:

                print(f"Unexpected item format in section '{section}': {items}")



        elif section == "general_information":

            # Traiter la section des informations générales

            for item in items:

                if isinstance(item, dict) and "key" in item and "value" in item:

                    knowledge["general_information"].append(item)

                else:

                    print(f"Unexpected item format in section '{section}': {item}")



        elif section == "faq":

            # Traiter la section FAQ

            for item in items:

                if isinstance(item, dict) and "question" in item and ("answer" in item or "response" in item):

                    # Support both "answer" and "response"

                    knowledge["faq"].append({

                        "question": item["question"],

                        "answer": item.get("answer", item.get("response", ""))

                    })

                else:

                    print(f"Unexpected item format in section '{section}': {item}")



        elif section == "questions_and_responses":

            # Traiter la section des questions-réponses (si différente de FAQ)

            for item in items:

                if isinstance(item, dict) and "question" in item and "response" in item:

                    knowledge["questions_and_responses"].append({

                        "question": item["question"],

                        "response": item["response"]

                    })

                else:

                    print(f"Unexpected item format in section '{section}': {item}")



        else:

            # Section inconnue

            print(f"Unknown section '{section}', skipping.")



    return knowledge



# Charger et prétraiter la base de connaissances

with open('archibald_knowledge.json', 'r', encoding='utf-8') as file:

    raw_knowledge_base = json.load(file)



knowledge_base = preprocess_knowledge(raw_knowledge_base)  # Prétraitement ici



# Debugging utilities

def debug(message):

    print(f"DEBUG: {message}")



# Extract date from French messages

MONTHS_FR = {

    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,

    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12

}



def parse_date_localized(date_string, locale="fr_FR"):

    try:

        date_string = date_string.strip()

        match = re.search(r"(\d{1,2})\s(\w+)\s(\d{4})", date_string, re.IGNORECASE)

        if match:

            day = int(match.group(1))

            month_name = match.group(2).lower()

            year = int(match.group(3))

            month = MONTHS_FR.get(month_name)

            if month:

                parsed_date = datetime(year, month, day)

                return parsed_date.date()

        return parse(date_string, fuzzy=True).date()

    except Exception as e:

        debug(f"Error during parsing: {e}")

        return None


def parse_relative_date(user_message):
    """
    Détecte et convertit les expressions relatives de date en format YYYY-MM-DD.
    Exemples : "aujourd'hui", "demain", "dans trois jours", "le 8 mars"
    """
    today = datetime.today()
    user_message = user_message.lower().strip()

    # Vérifier si "aujourd'hui" est bien compris
    if "aujourd'hui" in user_message or "aujourdhui" in user_message:
        print("DEBUG: Date détectée - Aujourd'hui")
        return today.date()
    if "demain" in user_message:
        print("DEBUG: Date détectée - Demain")
        return (today + timedelta(days=1)).date()
    if "après-demain" in user_message:
        print("DEBUG: Date détectée - Après-demain")
        return (today + timedelta(days=2)).date()

    # Expressions avec "dans X jours"
    match_relative = re.search(r"dans (\d+) jours?", user_message)
    if match_relative:
        days_ahead = int(match_relative.group(1))
        return (today + timedelta(days=days_ahead)).date()

    # Expressions avec une date explicite comme "le 8 mars"
    match_explicit = re.search(r"le (\d{1,2}) (\w+)", user_message)
    if match_explicit:
        day = int(match_explicit.group(1))
        month_name = match_explicit.group(2)

        MONTHS_FR = {
            "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
        }

        if month_name in MONTHS_FR:
            year = today.year
            parsed_date = datetime(year, MONTHS_FR[month_name], day).date()

            if parsed_date < today.date():
                parsed_date = datetime(year + 1, MONTHS_FR[month_name], day).date()

            return parsed_date

    return None  # Aucun match trouvé


def detect_language(user_message):

    """

    Détecte la langue du message utilisateur, avec des règles spécifiques pour des formats attendus.

    """

    try:

        # Vérification de mots-clés typiques en anglais (comme les mois)

        english_months = [

            "january", "february", "march", "april", "may", "june",

            "july", "august", "september", "october", "november", "december"

        ]

        if any(month in user_message.lower() for month in english_months):

            return "en"

        

        # Utiliser la bibliothèque de détection pour les autres cas

        lang = detect(user_message)

        print(f"Detected language: {lang}")

        return lang

    except Exception as e:

        print(f"Language detection failed: {e}")

        return "en"  # Fallback to English



def translate_with_dictionary(text, target_language):

    translator = Translator(to_lang=target_language)

    return translator.translate(text)


def extract_info(user_message):
    """
    Analyse le message pour extraire uniquement les informations pertinentes.
    - Ne cherche une date QUE si la question concerne les horaires.
    - Ne demande pas la composition du groupe sauf pour un tarif.
    """
    try:
        is_schedule = "horaire" in user_message.lower() or "ouvert" in user_message.lower()
        is_price = "tarif" in user_message.lower() or "prix" in user_message.lower()

        date = parse_relative_date(user_message) if is_schedule else None

        # Ne cherche la composition du groupe que si on parle des tarifs
        adults = children = []
        if is_price:
            adults_match = re.search(r"(\d+)\sadultes?", user_message)
            adults = int(adults_match.group(1)) if adults_match else 0

            children_matches = re.findall(r"(\d+)\s(enfants?|ans)", user_message)
            children = [int(match[0]) for match in children_matches]

        return {
            "date": date.isoformat() if date else None,
            "adults": adults,
            "children": children,
            "is_schedule": is_schedule,
            "is_price": is_price
        }

    except Exception as e:
        print(f"Erreur lors de l'extraction des informations: {e}")
        return {}


def get_opening_status(date, schedule):

    """

    Vérifie si le phare est ouvert pour une date donnée, en tenant compte des horaires réguliers et exceptionnels.

    """

    if not date:

        return "Date non spécifiée. Veuillez indiquer une date pour vérifier les horaires."



    date_obj = datetime.strptime(date, "%Y-%m-%d").date()



    # Vérification des ouvertures exceptionnelles

    for period in schedule:

        if period.get("type") == "exceptional":

            exceptional_openings = period.get("exceptional_opening", [])

            for exception in exceptional_openings:

                exception_date = datetime.strptime(exception["date"], "%Y-%m-%d").date()

                if exception_date == date_obj:

                    return f"Ouverture exceptionnelle le {date} : {exception['hours']} (dernière montée à {exception['last_entry']})."



    # Vérification des ouvertures régulières

    day_number = date_obj.weekday()

    french_days = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']

    day_name = french_days[day_number]



    for period in schedule:

        if period.get("type") == "regular":

            start_date = datetime.strptime(period["start_date"], "%Y-%m-%d").date()

            end_date = datetime.strptime(period["end_date"], "%Y-%m-%d").date()

            if start_date <= date_obj <= end_date and day_name in period.get("days_open", []):

                return f"Ouvert le {date} : {period['hours']} (dernière montée à {period['last_entry']})."



    # Si aucune correspondance n'est trouvée

    return f"Fermé le {date}."

def calculate_pricing(adults, children):
    """
    Calcule le tarif total pour un groupe donné.
    Toujours afficher les prix unitaires et avertir sur la fiabilité du calcul.
    """
    adult_price = 7
    child_price = 4
    free_below_age = 5
    adult_age_threshold = 13

    if adults == 0 and children:
        adults = 1  # Ajouter un adulte par défaut

    total_price = adults * adult_price
    child_details = []

    for child in children:
        if child < free_below_age:
            child_details.append(f"{child} ans (gratuit)")
        elif child >= adult_age_threshold:
            child_details.append(f"{child} ans ({adult_price}€ - tarif adulte)")
            total_price += adult_price
        else:
            child_details.append(f"{child} ans ({child_price}€)")
            total_price += child_price

    warning_message = (
        "⚠️ Je suis un vieux gardien et parfois je peux mal comprendre. "
        "Vérifiez toujours les prix sur le site officiel : "
        "👉 https://phareducapferret.com/horaires-et-tarifs/"
    )

    return total_price, adult_price, child_price, child_details, warning_message



def detect_pet_related_query(user_message):

    dog_keywords = ["chien", "toutou", "cabot", "canidé", "dog"]

    cat_keywords = ["chat", "minou", "félin","cat", "kitty"]

    general_pet_keywords = ["animal", "animaux", "pets"]



    contains_dog = any(keyword in user_message.lower() for keyword in dog_keywords)

    contains_cat = any(keyword in user_message.lower() for keyword in cat_keywords)

    contains_general_pet = any(keyword in user_message.lower() for keyword in general_pet_keywords)



    return {

        "dog": contains_dog,

        "cat": contains_cat,

        "general_pet": contains_general_pet

    }

def create_prompt(user_message_translated, extracted_info, lang):
    print(f"Creating prompt for: {user_message_translated}")
    print("Extracted information:", extracted_info)

    is_schedule = extracted_info.get("is_schedule", False)
    is_price = extracted_info.get("is_price", False)
    adults = extracted_info.get("adults", 1)
    children = extracted_info.get("children", [])

    response_parts = []

    # 🕒 Horaires → Répondre directement sans exiger plus d'infos
    if is_schedule:
        response_parts.append(
            "📌 Les horaires du phare changent selon la saison ! "
            "Vérifiez-les toujours ici : [🕒 Voir les horaires](https://phareducapferret.com/horaires-et-tarifs/)"
        )

    # 🎟️ Tarifs → Donner directement les prix sans poser de questions inutiles
    if is_price:
        total_price, adult_price, child_price, child_details, warning_message = calculate_pricing(adults, children)
        details_str = ", ".join(child_details) if child_details else "Aucun enfant précisé"

        response_parts.append(
            f"🎟️ Tarifs : **{adult_price}€ par adulte**, **{child_price}€ par enfant**.\n"
            f"💰 Estimation pour {adults} adulte(s) et {details_str} : **{total_price}€**\n"
            f"{warning_message}"
        )

    # Si aucun tarif ni horaire, donner une réponse plus générique
    if not is_schedule and not is_price:
    response_parts.append(
        "Ahoy, cher visiteur ! 🌊 Je veille sur le phare du Cap Ferret, toujours prêt à vous guider. "
        "Vous pouvez consulter les horaires et tarifs ici : [Infos du phare](https://phareducapferret.com/horaires-et-tarifs/)."
    )

    final_response = " ".join(response_parts)

    # 🔹 Prompt final pour OpenAI
    prompt = f"""
    You are Archibald, the wise and slightly grumpy lighthouse keeper. 

    Respond in the detected language: {lang}.

    Speak warmly but concisely, using maritime metaphors and humor.

    Here is the user's question: "{user_message_translated}"

    Use this information: "{final_response.strip()}"

    Respond in the detected language: {lang}.
    """

    return prompt


# Limiter à 5 requêtes par session

def limit_requests():
    if "request_count" not in session:
        session["request_count"] = 0

    session["request_count"] += 1

    print(f"DEBUG: Nombre de requêtes actuelles : {session['request_count']}")

    if session["request_count"] > 5:
        return jsonify({"error": "Trop de requêtes ! ⛔ Reposez-vous un peu avant de continuer."}), 429

    return True


@app.route("/debug_knowledge", methods=["GET"])

def debug_knowledge():

    """

    Route de débogage pour afficher la base de connaissances prétraitée.

    """

    return jsonify(knowledge_base)



@app.route("/chat", methods=["POST"])

@cross_origin(origins=["https://phareducapferret.com"], supports_credentials=True)  # Use cross_origin here

def chat():

    user_message = request.json.get("message")

    print("Step 1: Received user message:", user_message)



    if not user_message:

        return jsonify({"error": "No message provided"}), 400



    # Détecter la langue

    lang = detect_language(user_message)

    print("Step 2: Detected language:", lang)



    # Traduire le message vers le français si ce n'est pas déjà en français

    if lang != "fr":

        try:

            translator_to_french = Translator(to_lang="fr")

            user_message_translated = translator_to_french.translate(user_message)

            print("Step 3: Translated message to French:", user_message_translated)

        except Exception as e:

            print(f"Error during translation: {e}")

            return jsonify({"error": "An error occurred while translating the message."}), 500

    else:

        user_message_translated = user_message



    # Extraire les informations du message traduit

    extracted_info = extract_info(user_message_translated)

    print("Step 4: Extracted information:", extracted_info)



    # Créer le prompt

    prompt = create_prompt(user_message_translated, extracted_info, knowledge_base, lang=lang)

    print("Step 5: Generated prompt:", prompt)



    # Appel à OpenAI pour générer la réponse

    try:

        print("Step 6: Sending prompt to OpenAI...")

        response = openai.ChatCompletion.create(

            model="gpt-4o-mini",

            messages=[

                {"role": "system", "content": "You are Archibald, the knowledgeable lighthouse keeper."},

                {"role": "user", "content": prompt},

            ],

            max_tokens=300,

            temperature=0.7,

        )

        # Traduire la réponse générée si nécessaire

        chat_response = response["choices"][0]["message"]["content"].strip()

        if lang != "fr":

            translator_to_user_lang = Translator(to_lang=lang)

            chat_response_translated = translator_to_user_lang.translate(chat_response)

            print("Step 6: Translated response to user's language:", chat_response_translated)

            return jsonify({"response": chat_response_translated})

        else:

            return jsonify({"response": chat_response})

    except Exception as e:

        print(f"Error during OpenAI call: {e}")

        return jsonify({"error": "An error occurred while processing your request."}), 500



if __name__ == "__main__":
    app.run(debug=True, host="100.0.0.98", port=5000)





