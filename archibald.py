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

secret_key = os.getenv('SECRET_KEY')

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

    try:

        date_match = re.search(r"\b(\d{1,2}\s(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s\d{4})\b", user_message, re.IGNORECASE)

        date = parse_date_localized(date_match.group(1)) if date_match else None

        adults_match = re.search(r"(\d+)\sadultes?", user_message)

        adults = int(adults_match.group(1)) if adults_match else 0

        children_matches = re.findall(r"(\d+)\s(enfants?|ans)", user_message)

        children = [int(match[0]) for match in children_matches]

        is_schedule = "horaire" in user_message.lower() or "ouvert" in user_message.lower()

        is_price = "tarif" in user_message.lower() or "prix" in user_message.lower()

        

        # Détecter les questions générales

        is_general_question = not (is_schedule or is_price or date)

        

        return {

            "date": date.isoformat() if date else None,

            "adults": adults,

            "children": children,

            "is_schedule": is_schedule,

            "is_price": is_price,

            "is_general_question": is_general_question,

        }

    except Exception as e:

        debug(f"Error extracting information: {e}")

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





def calculate_pricing(adults, children, pricing):

    """

    Calcule le tarif total pour les adultes et les enfants.

    Ajoute automatiquement un adulte si aucun n'est mentionné pour accompagner des enfants.

    """

    # Ajouter un adulte par défaut si aucun n'est mentionné

    if adults == 0 and children:

        adults = 1



    adult_price = pricing.get("adult_price", 7)

    child_price = pricing.get("child_price", 4)

    free_below_age = pricing.get("child_free_below_age", 5)

    adult_age_threshold = pricing.get("adult_age_threshold", 13)



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



    return total_price, child_details



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



def create_prompt(user_message_translated, extracted_info, knowledge_base, lang):

    print(f"Creating prompt for translated message: {user_message_translated}")

    print("Extracted information:", extracted_info)



    # Extraction des données nécessaires

    date = extracted_info.get("date")

    adults = extracted_info.get("adults", 1)

    children = extracted_info.get("children", [])

    pet_query = detect_pet_related_query(user_message_translated)

    is_schedule = extracted_info.get("is_schedule", False)

    pricing = knowledge_base.get("pricing", {})

    schedule = knowledge_base.get("schedule", [])

    faq = knowledge_base.get("faq", [])

    questions_and_responses = knowledge_base.get("questions_and_responses", [])



    # Gestion des horaires

    schedule_response = ""

    if date:

        schedule_response = get_opening_status(date, schedule)

    else:

        schedule_response = "Je n'ai pas détecté de date. Pouvez-vous préciser une date pour vérifier les horaires ?"



    # Gestion des tarifs

    pricing_response = ""

    if children or adults > 0:

        if adults == 0 and children:

            adults = 1

            pricing_response = (

                "Aucun adulte n'était mentionné, donc j'ai supposé qu'un adulte accompagnerait les enfants. "

            )

        total_price, child_details = calculate_pricing(adults, children, pricing)

        pricing_response += (

            f"Le tarif total est de {total_price}€ : {adults} adulte(s) et {len(children)} enfant(s) ({', '.join(child_details)})."

        )

    else:

        pricing_response = "Aucune demande de tarif mentionnée. Spécifiez la composition du groupe pour plus de détails."



    # Gestion des animaux

    pet_response = ""

    if pet_query["dog"] or pet_query["cat"] or pet_query["general_pet"]:

        pet_response = (

            "Ahoy, marin d'eau douce ! Ton compagnon à quatre pattes est le bienvenu dans les espaces extérieurs du Phare, "

            "mais il ne peut pas entrer dans la tour ni dans le blockhaus. Pendant que tu explores, ton fidèle ami pourra profiter de l'air marin, accompagné d'un humain, bien sûr."

        )



    # Construction de la réponse finale

    response_parts = [

        f"Horaires pour le {date}: {schedule_response}" if date else schedule_response,

        pricing_response,

        pet_response,

    ]

    final_response = " ".join([part for part in response_parts if part])



    # Construire le prompt final

    prompt = f"""

    You are Archibald, the wise and slightly grumpy keeper of the Cap Ferret Lighthouse. 

    Respond in the detected language: {lang}.

    Speak warmly but concisely (no more than 450 characters), using maritime metaphors and your deep passion for the lighthouse.

    Here is the user's question: "{user_message_translated}"

    Use this information to craft your response: "{final_response.strip()}"

    Respond in the detected language: {lang}.

    """

    return prompt







# Limiter à 5 requêtes par session

def limit_requests():

    """

    Vérifie si l'utilisateur a atteint la limite de requêtes dans une session.

    """

    if "request_count" not in session:

        session["request_count"] = 0

    session["request_count"] += 1

    print(f"Current request count: {session['request_count']}")  # Debugging log

    if session["request_count"] > 5:

        print("Request limit exceeded.")  # Debugging log

        return False

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
    app.run(debug=True, host="10.100.0.244", port=5000)





