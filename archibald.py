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
    Analyse le message et extrait :
    - Une date si l'utilisateur demande un horaire.
    - Une demande de prix.
    - Une question sur les animaux.
    """
    try:
        # Identifier si la question porte sur les horaires
        is_schedule = any(word in user_message.lower() for word in ["horaire", "ouvert", "fermé", "heures", "temps"])

        # Identifier si la question porte sur les tarifs
        is_price = any(word in user_message.lower() for word in ["tarif", "prix", "combien", "coût"])

        # Identifier si la question porte sur les animaux
        is_pet = any(word in user_message.lower() for word in ["chien", "toutou", "cabot", "canidé", "dog", "chat", "minou", "félin","cat", "kitty", "oiseaux", "animal", "animaux", "pets", "perroquet", "canari", "hamster"])

        # Détecter la date si c'est une question d'horaire
        date = parse_relative_date(user_message) if is_schedule else None

        return {
            "date": date.isoformat() if date else None,
            "is_schedule": is_schedule,
            "is_price": is_price,
            "is_pet": is_pet
        }

    except Exception as e:
        print(f"Erreur lors de l'extraction des informations: {e}")
        return {}


def create_prompt(user_message_translated, extracted_info, lang):
    print(f"Creating prompt for: {user_message_translated}")
    print("Extracted information:", extracted_info)

    is_schedule = extracted_info.get("is_schedule", False)
    is_price = extracted_info.get("is_price", False)
    is_pet = extracted_info.get("is_pet", False)

    response_parts = []

    # 🔹 Si la question concerne les horaires, il redirige directement vers la page officielle
    if is_schedule:
        response_parts.append(
            "📌 Les horaires du phare peuvent varier en fonction de la saison. "
            "Consultez-les ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/)."
        )

    # 🔹 Si la question concerne les tarifs, il annonce le prix et redirige
    if is_price:
        response_parts.append(
            "🎟️ Le tarif d’entrée est de **7€ pour les adultes** et **4€ pour les enfants**.\n"
            "📌 Consultez les détails ici : [🕒 Voir les horaires et tarifs](https://phareducapferret.com/horaires-et-tarifs/)."
        )

    # 🔹 Si la question concerne les animaux, il informe des règles
    if is_pet:
        response_parts.append(
            "🐾 Les animaux de compagnie sont **autorisés dans le parc et la boutique**, mais **interdits dans la tour et le blockhaus**.\n"
            "📌 Lors de votre visite, ils doivent rester sous surveillance humaine au pied du phare."
        )

    # 🔹 Réponse par défaut si aucune catégorie ne correspond
    if not (is_schedule or is_price or is_pet):
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




