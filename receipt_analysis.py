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
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import base64
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
import os
import re

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

def analyze_receipt(input_file_name):
    #print("Starting receipt analysis")
    # Loading the environment variables
    #load_dotenv()

    # Instantiating the OpenAI client
    openai_client = AzureOpenAI(
        azure_endpoint="https://aisdevelopment.openai.azure.com/",
            api_key="DTyQG79lV7tPjYYFAB9sGzYe8MkQSrdLsosDYlUEIqAjNQ9NDtZZJQQJ99BFACYeBjFXJ3w3AAABACOGBm6d",
            api_version="2024-12-01-preview",
        )
    
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint="https://testreadreciept.cognitiveservices.azure.com/",
        credential=AzureKeyCredential("39iwdH3cbVrTiGFLksknxzvPZDP2qBD6E5QQ97HgsyKg19ou4odPJQQJ99BFACYeBjFXJ3w3AAALACOGgR2Z")
    )
    
    with open(input_file_name, 'rb') as image_file:
        #use the reciept model
        poller = document_intelligence_client.begin_analyze_document(
            "prebuilt-receipt", 
            image_file,
            content_type="application/octet-stream"
        )

    extracted_items = ""
    result = poller.result()
    outputs = []

    #display results
    #print("Receipt Analysis Results:")
    finalCost = 0
    if result.documents:
        for document in result.documents:       
            items = document.fields["Items"].value_array

            for i, item in enumerate(items):
                #get price
                item_value = item.value_object
                if item_value.get("TotalPrice"):
                    item_total = item_value.get("TotalPrice").content
                else:
                    item_total = "N/A"

                item_total = re.sub(r'[^\d.\-]', '', item_total).strip()
                if item_total.endswith('-'):
                    item_total = item_total[:-1].strip()
                
                try:
                    if item_total != "N/A":
                        finalCost += float(item_total)
                except (ValueError, AttributeError):
                    print("Error parsing receipt item total:", item_total)



                #get item name
                possible_name_keys = ["Name", "Description", "Item", "Product", "Title"]
                item_name = None
                for key in possible_name_keys:
                    field = item_value.get(key)
                    if field and getattr(field, "content", "").strip():
                        item_name = field.content.strip()
                        break
                if not item_name:
                    item_name = "Unnamed Item"

                outputs.append(item_name + " || total: $" + item_total)
            
            extracted_items = "\n".join(outputs)

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
                    }
                },
                "required": ["data"]
            }
        }
    ]
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """You're a helpful assistant that categorizes spending from receipts into budget categories and generates graphs.
                    When given receipt items, you must:
                    1. Categorize each item into a category like Food, Health, Leisure, Household, or Other
                    2. Provide further separation into each category by dividing items into subcategories like Groceries-produce, groceries-meat, restaurant-fast food, restaurant-dine in, etc.
                    3. Group totals by category and find the total spending in each category by manually adding each item in that category
                    4. Acquire the total spending across all categories by adding up the totals of each category
                    5. Return the data by calling the plot_pie_chart function with a data dictionary

                    IMPORTANT: Always call the plot_pie_chart function with the spending data. If you only have one category of items, provide the pie chart with the subcategories. If you have multiple categories, provide the pie chart with the main categories that dont have subcategories and the subcategories that compromise a main category.

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
    if message.function_call:
        arguments = json.loads(message.function_call.arguments)
        image_path = plot_pie_chart(arguments)
    else:
        # In case GPT didn't use the function call
        print(message.content)
            
    outputs.append(f"Subtotal: ${finalCost}")
    return "\n".join(outputs), image_path
