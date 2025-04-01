from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    ime = "Aljaž Žiga"
    return render_template("index.html", ime = ime)


app.run(debug = True)