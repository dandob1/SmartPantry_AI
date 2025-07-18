from flask import Flask, render_template, request
import os
from receipt_analysis import analyze_receipt
import magic
import time

app = Flask(__name__)
app.secret_key = "poop fart"
app.debug = True

SUPPORTED_FORMATS = [
    "PDF", "JPEG", "JPG", "PNG"
]

ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/jpg"
}


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    image_path = None
    error = None

    if request.method == "POST":
        file = request.files["receipt"]
        if file:
            
            filepath = os.path.join('uploads', file.filename)
            file.save(filepath)

            ext = os.path.splitext(file.filename)[1][1:].upper()
            type = magic.from_file(filepath, mime=True)
            if ext not in SUPPORTED_FORMATS or type not in ALLOWED_TYPES:
                error = f"Unsupported or corrupted file. Allowed types: {', '.join(SUPPORTED_FORMATS)}."
            else:
                result, image_path = analyze_receipt(filepath)
    return render_template("home.html", result=result, image_path=image_path, error=error)

if __name__ == "__main__":
    app.run()