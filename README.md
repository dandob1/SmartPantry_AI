NEED TO WRITE A README

Libraries:
- pip install openai
- pip install python-dotenv
- pip install matplotlib
- pip install azure-ai-documentintelligence
- pip install python-magic-bin

To run the program begin by running **init_db.py** to initialize the database. The run app.py to run the program.

Uses AI to:
- extract items from a receipt
- categorize items into a category and subcategory
- clean receipt information (i.e. "ORGANIC RND YELLOW TORT. CHIPS" = "Organic Yellow Tortilla Chips" or "GHRDL CAB MATINEE" = "Ghirardelli Matinee Chocolate")
- prevent duplicate entries in the history page (i.e. if "granny smith apple" is entered, it will warn about entry of "green apple")
