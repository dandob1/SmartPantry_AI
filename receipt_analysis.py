#Download the following presets:
#%%capture
#%pip install openai
#%pip install python-dotenv
#%pip install matplotlib
#%pip install pillow
#%pip install azure-ai-documentintelligence
#%pip install flask

import json
import time
from openai import AzureOpenAI
from dotenv import load_dotenv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import base64
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
import os
import re
import sqlite3

#pie chart plotting function
def plot_pie_chart(data):
    if not data:
        print("No data to plot.")
        return None

    labels = list(data.keys())
    values = list(data.values())

    if not any(values):
        print("Data values are all zero or missing.")
        return None

    plt.figure(figsize=(7, 7))
    plt.pie(values, labels=labels, autopct='%1.1f%%', colors=plt.cm.Pastel2.colors)
    plt.axis('equal')
    plt.tight_layout()
    
    output_path = os.path.join("static", "pie_chart.png")
    plt.savefig(output_path)
    plt.close()

    return "/" + output_path

#the receipt analysis function
def analyze_receipt(input_file_name, uid):
    #print("Starting receipt analysis")
    # Loading the environment variables
    #load_dotenv()

    # Instantiating the OpenAI client
    openai_client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint="https://pprojects.openai.azure.com/",
        api_key="60k6pEridppQUi1HWnrw031CKwrpjB4EIFm9EeFVdp1BFdZTo5v1JQQJ99BJACYeBjFXJ3w3AAABACOG0e1A",
    )
    #receipt reader client
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint="https://receiptreaderpp.cognitiveservices.azure.com/",
        credential=AzureKeyCredential("DWxHgv6diKEFUsYS2vyYt0V8C696GwByccLIMW5NPj159zKuccbVJQQJ99BJACYeBjFXJ3w3AAALACOGWVPF")
    )
    #open image
    with open(input_file_name, 'rb') as image_file:
        #use the reciept model
        poller = document_intelligence_client.begin_analyze_document(
            "prebuilt-receipt", 
            image_file,
            content_type="application/octet-stream"
        )
    #connect to the database
    conn = sqlite3.connect("db.db")
    cur = conn.cursor()
#variables used
    extracted_items = ""
    result = poller.result()
    outputs = []
    items_for_db = []

    #display results
    #print("Receipt Analysis Results:")
    finalCost = 0
    if result.documents:
        for document in result.documents:       
            items = document.fields["Items"].value_array

            for item in items:
                #get price
                item_value = item.value_object
                if item_value.get("TotalPrice"):
                    item_total = item_value.get("TotalPrice").content
                else:
                    item_total = "0.00"
                #clean up the price
                item_total = re.sub(r'[^\d.\-]', '', item_total).strip()
                if item_total.endswith('-'):
                    item_total = item_total[:-1].strip()
                #convert to float and round
                try:
                    price = round(float(item_total), 2)
                except (ValueError, TypeError):
                    price = 0.00

                finalCost += price

                #get item name
                possible_name_keys = ["Name", "Description", "Item", "Product", "Title"]
                item_name = None
                #try to find the item name in the possible keys
                for key in possible_name_keys:
                    field = item_value.get(key)
                    if field and getattr(field, "content", "").strip():
                        item_name = field.content.strip()
                        break
                if not item_name:
                    item_name = "Unnamed Item"

                category    = item_value.get("Category",    {}).get("content", "Other")
                subcategory = item_value.get("Subcategory", {}).get("content", "")

                outputs.append(item_name + " || Price: $" + f"{price:.2f}")

                items_for_db.append((item_name, price, category, subcategory))

            
            extracted_items = "\n".join(outputs)
    #define functions
    functions = [
        {
            "name": "plot_pie_chart",
            "description": "Plots a pie chart based on categorized spending data",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "Dictionary with category names as keys and spending amounts as values",
                        "additionalProperties": {
                            "type": "number"
                        }
                    },
                    "items": {
                    "type": "array",
                    "description": "Each item with its name, price, category & subcategory",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":        { "type": "string" },
                            "price":       { "type": "number" },
                            "category":    { "type": "string" },
                            "subcategory": { "type": "string" }
                        },
                        "required": ["name","price","category","subcategory"]
                    }
                }
                },
                "required": ["data", "items"]
            }
        }
    ]
    #get response from OpenAI
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """You're a helpful assistant that categorizes spending from receipts into budget categories and generates graphs.
                    When given receipt items, you must:
                    1. Categorize each item into a category like Food, Health, Leisure, Household, or Other. ITS CRITICAL you adhere to choose only from the categories provided:
                        - Groceries... subcategories: Produce, Meat & Poultry, Dairy, Bakery, Pantry & Dry Goods, Frozen Foods, Snacks & Candy, Beverages (non-alcoholic), Alcoholic Beverages, Household Supplies, Pharmacy / Health Goods, Extras
                        - Dining Out... subcategories: Fast Food, Casual Dining, Fine Dining, Coffee Shops, Takeout & Delivery, Bars & Pubs
                        - Transportation... Subcategories: Gasoline, Parking, Public Transit, Car Maintenance, Tolls & Fees, Rideshare (Uber/Lyft), Travel
                        - Clothing & Accessories... subcategories: Mens Clothing, Womens Clothing, Childrens Clothing, Footwear, Accessories
                        - Leisure & Entertainment... subcategories: Movies & Events, Streaming Services, Games & Toys, Hobbies & Crafts, Sports & Fitness, Extras
                        - If an item does not fit into any of these categories, classify it as Other.
                    2. Provide further separation into each category by dividing items into subcategories like Groceries-produce, groceries-meat, restaurant-fast food, restaurant-dine in, etc.
                    3. Group totals by category and find the total spending in each category by manually adding each item in that category
                    4. Acquire the total spending across all categories by adding up the totals of each category
                    5. Return both:
                       • a top-level “data” object mapping each category→total
                       • an “items” array of {name,price,category,subcategory}
                    by calling the plot_pie_chart function with both keys.

                    IMPORTANT: Always call the plot_pie_chart function with the spending data. If you only have one category of items, provide the pie chart with the subcategories. If you have multiple categories, provide the pie chart with just the main categories.

                    Example format for function call:
                    - If multiple categories: {"Food": 22.35, "Health": 15.50, "Household": 8.75}
                    - If single category with subcategories: {"Groceries-Produce": 7.42, "Groceries-Pantry": 8.95, "Groceries-Meat": 3.29, "Snacks": 2.69}"""
            },
            {
                "role": "user",
                "content": f"""Here is a list of items from a receipt: {extracted_items}
                    Please categorize these items and create a pie chart showing the spending breakdown."""
            }
        ],
        functions=functions,
        function_call="auto"
    )
    message = response.choices[0].message
    image_path = None
    #get information from the response
    if message.function_call:
        arguments = json.loads(message.function_call.arguments)
        classified = arguments.get("items", [])
        if "data" in arguments:
            totals = arguments["data"]
        else:
            totals = {}
            for it in classified:
                cat = it["category"]
                totals[cat] = totals.get(cat, 0.0) + it["price"]

        items_for_db.clear()
        #prepare them for database insertion
        for item in classified:
            name = item["name"]
            price = item["price"]
            category = item["category"]
            subcategory = item["subcategory"]

            row = (name, price, category, subcategory)
            items_for_db.append(row)

        image_path = plot_pie_chart(totals)

    raw_names = [row[0] for row in items_for_db]
    cleanup = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    """You are a data-cleaning assistant.
                    Given a JSON array of product descriptions OCRd from grocery receipts, return ONLY a JSON array of human-friendly product names, e.g.:
                    '["ORGANIC RND YELLOW TORT. CHIPS", …] → ["Organic Yellow Tortilla Chips", …]'
                    DO NOT include any explanation—just output the JSON array."""
                )
            },
            {
                "role": "user",
                "content": json.dumps(raw_names)
            }
        ]
    )
    clean_names = json.loads(cleanup.choices[0].message.content)
    error = None
    # rebuild items_for_db with the cleaned names
    original_items = items_for_db.copy()
    #check if all rows outputted
    if len(clean_names) != len(original_items):
        error = f"Sorry, we tooted. Missing some items: {len(clean_names)} found vs {len(original_items)} in the receipt"
    items_for_db = [
        (clean_name, price, category, subcategory)
        for ( _ , price, category, subcategory), clean_name
        in zip(original_items, clean_names)
    ]
    #put into first table
    cleaned = sum(price for (name, price, cat, sub) in items_for_db)
    cur.execute(
        "INSERT INTO receipt (uid, total_spend, image_path) VALUES (?, ?, ?)",
        (uid, cleaned, image_path)
    )
    rid = cur.lastrowid
    #second table
    for name, price, category, subcategory in items_for_db:
        cur.execute(
            "INSERT INTO receiptData (rid, itemName, itemPrice, category, subcategory) VALUES (?, ?, ?, ?, ?)",
            (rid, name, price, category, subcategory)
        )

    conn.commit()
    conn.close()
            
    return items_for_db, image_path, error

#ai that will classify individual items added
def classify_item(name: str, existing_items: list[str]):
    client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint="https://pprojects.openai.azure.com/",
        api_key="60k6pEridppQUi1HWnrw031CKwrpjB4EIFm9EeFVdp1BFdZTo5v1JQQJ99BJACYeBjFXJ3w3AAABACOG0e1A",
    )
    #provide system prompt, same as before
    system = {
        "role": "system",
        "content": (
            """You're a helpful assistant that categorizes spending from receipts into budget categories.
            You will receive:
                • existing_items: an array of strings (items already in the user's history)
                • new_item: a single string
            First, very carefully examine each item and do a case-insensitive substring check: if new_item is already represented in existing_items, return exactly `{ \"duplicate\": true }` and nothing else. If an item such as purple grapes is already in the dictionary, allow the inserion of green grapes. If windex is already inserted, allow window cleaner.. etc. Do not allow exact duplicated like oreo cookies and oreos, or oreo.
            Then you MUST, classify a single grocery item into one of these main categories, ITS CRITICAL you adhere to choose only from the categories provided:
                        - Groceries... subcategories: Produce, Meat & Poultry, Dairy, Bakery, Pantry & Dry Goods, Frozen Foods, Snacks & Candy, Beverages (non-alcoholic), Alcoholic Beverages, Household Supplies, Pharmacy / Health Goods, Extras
                        - Dining Out... subcategories: Fast Food, Casual Dining, Fine Dining, Coffee Shops, Takeout & Delivery, Bars & Pubs
                        - Transportation... Subcategories: Gasoline, Parking, Public Transit, Car Maintenance, Tolls & Fees, Rideshare (Uber/Lyft), Travel
                        - Clothing & Accessories... subcategories: Mens Clothing, Womens Clothing, Childrens Clothing, Footwear, Accessories
                        - Leisure & Entertainment... subcategories: Movies & Events, Streaming Services, Games & Toys, Hobbies & Crafts, Sports & Fitness, Extras
                        - If an item does not fit into any of these categories, classify it as Other.
            Output EXACTLY one JSON object, nothing else if you passed step one, e.g.: '{"category":"Groceries","subcategory":"Produce"}'"""
        )
    }

    user = {
        "role": "user",
        "content": json.dumps({
            "existing_items": existing_items,
            "new_item": name
        })
    }

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[system, user],
        temperature=0,
    )

    answer = response.choices[0].message.content.strip()
    answer = re.sub(r"^```json\s*|```$", "", answer, flags=re.IGNORECASE).strip()

    try:
        obj = json.loads(answer)
    except json.JSONDecodeError:
        return "Other", ""
    
    if obj.get("duplicate"):
        return None, None
    else:
        return obj.get("category", "Other"), obj.get("subcategory", "")
    
def recipe(pantry_items, difficulty, srequest=""):
    client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint="https://pprojects.openai.azure.com/",
        api_key="60k6pEridppQUi1HWnrw031CKwrpjB4EIFm9EeFVdp1BFdZTo5v1JQQJ99BJACYeBjFXJ3w3AAABACOG0e1A",
    )

    # the 2 prompts
    if difficulty == "easy":
        system_prompt = """You are a professional chef specializing in coming up with creative recipes. 
        Create recipes that require basic to average cooking skills, use common techniques, and have clear step-by-step instructions.
        Focus on recipes that can be completed in one hour or less with basic kitchen equipment.
        You will be provided a list of items, use those to come up with your recipe and assume they only have extra basic condiments and seasonings. 
        IMPORTANT: You do not have to use all of the ingredients, only use the ones that make sense. Also adhere to all special requests as best you can.
        CRITICAL: If you cannot come up with any appetizing recipe that is normal for most people from those ingredients provided simply say: 'Sorry, I could not make a recipe using only those ingredients. Try adding more and try again!' """
    else:
        system_prompt = """You are a professional chef who creates delicious but relatively simple meals. 
        You will be provided a list of panty items, ignore them and come up with the best tasting dish possible, adhere to all special requests as best you can.
        Be creative and come up with a classic and well known dish that anyone and everyone would like."""

    if pantry_items:
        pantry_list = ", ".join(pantry_items)  
    else: 
        pantry_list = "no specific items"
    user_prompt = f"""Here is the pantry items: {pantry_list}
            
            Please provide:
            1. Recipe name
            2. Complete ingredients list (including quantities)
            3. Step-by-step cooking instructions
            4. Estimated cooking time
            5. Number of servings
            6. Estimated nutrition facts
            
            Assume I have basic ingredients like salt, pepper, oil, eggs, and common spices."""
    if srequest:
        finalPrompt = f"Special request: {srequest}\n\n{user_prompt}"
    else:
        finalPrompt = user_prompt

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
        {
            "role": "system", 
            "content": system_prompt
        },
        {
            "role": "user", 
            "content": finalPrompt
        }
    ],
            temperature=0.7,
            max_tokens=1500
        )
        
        result = completion.choices[0].message.content
        return result
        
    except Exception as e:
        return f"Sorry, I couldn't generate a recipe at this time. Please try again later. Error: {str(e)}"