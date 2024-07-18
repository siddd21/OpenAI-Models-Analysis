from flask import Flask, request, jsonify, render_template
import requests
from datetime import datetime, timezone
import re

app = Flask(__name__)

def fetch_models(token):
    #("Fetching models...")
    url = "https://aiproxy.sanand.workers.dev/openai/v1/models"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        models = response.json()["data"]
        #(f"Fetched {len(models)} models")
        return models
    else:
        #(f"Failed to fetch models: {response.status_code}")
        raise Exception(f"Failed to fetch models: {response.status_code}")

def parse_date(unix_time):
    dt = datetime.fromtimestamp(int(unix_time), tz=timezone.utc)
    #(f"Parsed date: {unix_time} -> {dt}")
    return dt

def extract_conditions(question_lines):
    #("Extracting conditions from question:")
    conditions = []
    for line in question_lines:
        match = re.match(r'(\d+) points? if (.*)', line)
        if match:
            points, condition = match.groups()
            conditions.append((int(points), condition))
            #(f"Extracted condition: {points} points if {condition}")
    return conditions

def process_question(question, models):
    #("Processing question...")
    points = 0
    question_lines = question.split('\n')
    
    #("Extracting cutoff date...")
    cutoff_date_match = re.search(r'created before (\d{1,2} \w+ \d{4})', question_lines[0])
    if cutoff_date_match:
        cutoff_date_str = cutoff_date_match.group(1)
        cutoff_date = datetime.strptime(cutoff_date_str, "%d %B %Y").replace(tzinfo=timezone.utc)
        #(f"Cutoff date: {cutoff_date}")
    else:
        cutoff_date = datetime.max.replace(tzinfo=timezone.utc)
        #("No cutoff date found, using max date")
    
    #("Sorting and filtering models...")
    sorted_models = sorted(models, key=lambda x: x["created"], reverse=True)
    filtered_models = [model for model in sorted_models if parse_date(model["created"]) < cutoff_date]
    #(f"Filtered models: {len(filtered_models)}")
    
    model_dict = {model["id"]: model for model in filtered_models}
    
    conditions = extract_conditions(question_lines[2:-1])  # Skip the first two lines and the last line
    
    for point_value, condition in conditions:
        #(f"Processing condition: {condition}")
        if "was created on" in condition:
            match = re.search(r'(.*) was created on (\d{4}-\d{2}-\d{2})', condition)
            if match:
                model_name, date_str = match.groups()
                expected_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                #(f"Checking if {model_name} was created on {expected_date}")
                if model_name in model_dict:
                    model_date = parse_date(model_dict[model_name]["created"])
                    #(f"{model_name} creation date: {model_date}")
                    if model_date.date() == expected_date.date():
                        points += point_value
                        #(f"Condition met! Added {point_value} points")
                else:
                    print(f"Model {model_name} not found in fetched models")
        elif "is located at index" in condition:
            match = re.search(r'(.*) is located at index (\d+)', condition)
            if match:
                model_name, index = match.groups()
                #(f"Checking if {model_name} is at index {index}")
                if model_name in model_dict:
                    actual_index = filtered_models.index(model_dict[model_name])
                    #(f"{model_name} is actually at index {actual_index}")
                    if actual_index == int(index):
                        points += point_value
                        #(f"Condition met! Added {point_value} points")
                else:
                    print(f"Model {model_name} not found in fetched models")
        elif "was created" in condition and "models before" in condition:
            match = re.search(r'(.*) was created (\d+) models before (.*)', condition)
            if match:
                model1, num, model2 = match.groups()
                #(f"Checking if {model1} was created {num} models before {model2}")
                if model1 in model_dict and model2 in model_dict:
                    index1 = filtered_models.index(model_dict[model1])
                    index2 = filtered_models.index(model_dict[model2])
                    #(f"{model1} index: {index1}, {model2} index: {index2}")
                    if index1 - index2 == int(num):
                        points += point_value
                        #(f"Condition met! Added {point_value} points")
                else:
                    print(f"Model {model1} or {model2} not found in fetched models")
        else:
            print(f"Unrecognized condition format: {condition}")
    
    #(f"Total points: {points}")
    return points

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    #("Received analyze request")
    data = request.json
    question = data.get('question')
    token = data.get('token')
    
    if not question or not token:
        #("Missing question or token")
        return jsonify({"error": "Missing question or token"}), 400
    
    try:
        #("Fetching models and processing question")
        models = fetch_models(token)
        result = process_question(question, models)
        #(f"Analysis complete. Result: {result}")
        return jsonify({"points": result})
    except Exception as e:
        #(f"Error during analysis: {str(e)}")
        return jsonify({"error": str(e)}), 500
