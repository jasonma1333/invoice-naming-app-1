from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Hello from Vercel! Deployment is working."

@app.route('/about')
def about():
    return "About page"
