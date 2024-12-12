import os
import json
import re
from dotenv import load_dotenv
from dateutil.parser import parse
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from langdetect import detect
from translate import Translator
import openai

# Load environment variables
load_dotenv()
secret_key = os.getenv('SECRET_KEY')
openai.api_key = secret_key

# Flask setup
app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = "archi33950baldBOT"

# Preprocess knowledge base
def preprocess_knowledge(raw_knowledge):
    """
    Transforms and preprocesses the JSON data to structure information into usable sections.
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
            for schedule_item in items:
                if isinstance(schedule_item, dict):
                    knowledge["schedule"].append(schedule_item)
        elif section == "pricing":
            if isinstance(items, dict):
                knowledge["pricing"] = items
        elif section == "general_information":
            for item in items:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    knowledge["general_information"].append(item)
        elif section == "faq":
            for item in items:
                if isinstance(item, dict) and "question" in item and ("answer" in item or "response" in item):
                    knowledge["faq"].append({
                        "question": item["question"],
                        "answer": item.get("answer", item.get("response", ""))
                    })
        elif section == "questions_and_responses":
            for item in items:
                if isinstance(item, dict) and "question" in item and "response" in item:
                    knowledge["questions_and_responses"].append(item)
    return knowledge

with open('archibald_knowledge.json', 'r', encoding='utf-8') as file:
    raw_knowledge_base = json.load(file)

knowledge_base = preprocess_knowledge(raw_knowledge_base)

# Utility functions
def debug(message):
    print(f"DEBUG: {message}")

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}

def parse_date_localized(date_string):
    try:
        date_string = date_string.strip()
        match = re.search(r"(\d{1,2})\s(\w+)\s(\d{4})", date_string, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))
            month = MONTHS_FR.get(month_name)
            if month:
                return datetime(year, month, day).date()
        return parse(date_string, fuzzy=True).date()
    except Exception as e:
        debug(f"Error during parsing: {e}")
        return None

def detect_language(user_message):
    try:
        english_months = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ]
        if any(month in user_message.lower() for month in english_months):
            return "en"
        return detect(user_message)
    except Exception as e:
        debug(f"Language detection failed: {e}")
        return "en"

def extract_info(user_message):
    try:
        date_match = re.search(r"\b(\d{1,2}\s(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s\d{4})\b", user_message, re.IGNORECASE)
        date = parse_date_localized(date_match.group(1)) if date_match else None
        adults_match = re.search(r"(\d+)\sadultes?", user_message)
        adults = int(adults_match.group(1)) if adults_match else 0
        children_matches = re.findall(r"(\d+)\s(?:enfants?|ans)", user_message)
        children = [int(match) for match in children_matches]
        is_schedule = "horaire" in user_message.lower() or "ouvert" in user_message.lower()
        is_price = "tarif" in user_message.lower() or "prix" in user_message.lower()
        return {
            "date": date.isoformat() if date else None,
            "adults": adults,
            "children": children,
            "is_schedule": is_schedule,
            "is_price": is_price
        }
    except Exception as e:
        debug(f"Error extracting information: {e}")
        return {}

def calculate_pricing(adults, children, pricing):
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

def get_opening_status(date, schedule):
    if not date:
        return "Date non spécifiée. Veuillez indiquer une date pour vérifier les horaires."

    date_obj = datetime.strptime(date, "%Y-%m-%d").date()

    for period in schedule:
        if period.get("type") == "exceptional":
            exceptional_openings = period.get("exceptional_opening", [])
            for exception in exceptional_openings:
                exception_date = datetime.strptime(exception["date"], "%Y-%m-%d").date()
                if exception_date == date_obj:
                    return f"Ouverture exceptionnelle le {date} : {exception['hours']} (dernière montée à {exception['last_entry']})."

    day_number = date_obj.weekday()
    french_days = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
    day_name = french_days[day_number]

    for period in schedule:
        if period.get("type") == "regular":
            start_date = datetime.strptime(period["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(period["end_date"], "%Y-%m-%d").date()
            if start_date <= date_obj <= end_date and day_name in period.get("days_open", []):
                return f"Ouvert le {date} : {period['hours']} (dernière montée à {period['last_entry']})."

    return f"Fermé le {date}."

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    lang = detect_language(user_message)

    if lang != "fr":
        translator_to_french = Translator(to_lang="fr")
        user_message_translated = translator_to_french.translate(user_message)
    else:
        user_message_translated = user_message

    extracted_info = extract_info(user_message_translated)

    date = extracted_info.get("date")
    adults = extracted_info.get("adults", 1)
    children = extracted_info.get("children", [])
    schedule_response = get_opening_status(date, knowledge_base["schedule"]) if date else "Veuillez préciser une date."

    pricing_response = ""
    if children or adults > 0:
        total_price, child_details = calculate_pricing(adults, children, knowledge_base["pricing"])
        pricing_response = f"Le tarif total est de {total_price}€."

    response = f"{schedule_response} {pricing_response}"
    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True, host='10.100.0.244', port=5000)
