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
    plt.title('Spending Breakdown by Category')
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
        azure_endpoint="https://aisdevelopment.openai.azure.com/",
            api_key="DTyQG79lV7tPjYYFAB9sGzYe8MkQSrdLsosDYlUEIqAjNQ9NDtZZJQQJ99BFACYeBjFXJ3w3AAABACOGBm6d",
            api_version="2024-12-01-preview",
        )
    #receipt reader client
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint="https://testreadreciept.cognitiveservices.azure.com/",
        credential=AzureKeyCredential("39iwdH3cbVrTiGFLksknxzvPZDP2qBD6E5QQ97HgsyKg19ou4odPJQQJ99BFACYeBjFXJ3w3AAALACOGgR2Z")
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

    # rebuild items_for_db with the cleaned names
    items_for_db = [
        (clean_names[i], price, cat, sub)
        for i, (_, price, cat, sub) in enumerate(items_for_db)
    ]

    #put into first table
    cur.execute(
        "INSERT INTO receipt (uid, total_spend, image_path) VALUES (?, ?, ?)",
        (uid, finalCost, image_path)
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
            
    return items_for_db, image_path