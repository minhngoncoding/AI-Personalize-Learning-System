from http.client import responses

from icecream import ic
from flask import Flask, render_template, request, session, redirect, url_for
from flask import render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import google.generativeai as genai
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
import re
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import openai  # don't go for upgraded version
import json
import requests
from flask_weasyprint import HTML, render_pdf
from weasyprint import CSS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'alpha-beta-gamma'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
API_KEY = "YOUR_API_KEY"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-002")

# Create a Markdown instance with the FencedCodeExtension
md = markdown.Markdown(extensions=[FencedCodeExtension()])



class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique = True)
    email = db.Column(db.String(50), unique = True)
    password = db.Column(db.String(80))
    courses = db.relationship('Course', backref='user', lazy=True)
    date_joined = db.Column(db.DateTime, default=datetime.now)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))




@app.route("/quiz_interface")
def quiz_interface():
    return render_template("home.html")


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if (request.method == "POST"):
        print(request.form)
        language = request.form["language"]
        questions = request.form["ques"]
        choices = request.form["choices"]
        #difficulty = request.form["diff"]
        prompt = f"Hello, please prepare a quick quiz on this programming language: {language} and prepare {questions} number of questions and for each of them keep {choices} number of choices, reply in the form of an object, make sure the response object contains topic, questions array containing question, choices and it's answer,print them in json format"

        response = model.generate_content(prompt)
        # ic(response)

        quiz_content= re.search(r'{.*}',response.parts[0].text, re.DOTALL).group()
        # print(response['choices'][0]['message']['content'])
        # quiz_content = response['choices'][0]['message']['content']
        #print(quiz_content)

        # Convert the content string to a dictionary
        # ic(response.parts[0].text[7:])
        quiz_content = json.loads(quiz_content)
        
        session['response'] = quiz_content
        # app.secret_key = os.environ.get("SECRET_KEY")

        return render_template("quiz.html", quiz_content=quiz_content)
    
    if request.method == "GET":
        score = 0
        actual_answers = []
        given_answers = list(request.args.values()) or []
        res = session.get('response', None)
        for answer in res["questions"]:
            actual_answers.append(answer["answer"])
        if len(given_answers)!= 0:
            ic(len(actual_answers), len(given_answers))
            for i in range(len(actual_answers)):
                actual_answers[i] = actual_answers[i].strip()
                given_answers[i] = given_answers[i].strip()
                if actual_answers[i] == given_answers[i] or actual_answers[i][0].lower() == given_answers[i][0].lower():
                    score=score+1
        return render_template("score.html", actual_answers=actual_answers, given_answers=given_answers, score=score)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        new_user = User(username=request.form['username'], email=request.form['email'], password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')




@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))




@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_authenticated:
        return render_template('dashboard.html', user=current_user)
    else:
        return redirect(url_for('login'))





@app.route('/')
def home():
    if current_user.is_authenticated:
        saved_courses = Course.query.filter_by(user_id=current_user.id).all()
        recommended_courses = generate_recommendations(saved_courses)
        return render_template('app.html', saved_courses=saved_courses, recommended_courses = recommended_courses, user=current_user)
    else:
        return redirect(url_for('login'))




@app.route('/course', methods=['GET', 'POST'])
@login_required
def course():
    if request.method == 'POST':
        course_name = request.form['course_name']
        completions = generate_text(course_name)
        rendered = render_template('courses/course1.html', completions=completions, course_name=course_name)
        new_course = Course(course_name=course_name, content=rendered, user_id=current_user.id)
        db.session.add(new_course)
        db.session.commit()
        return rendered
    return render_template('courses/course1.html')




@app.route('/r_course/<course_name>', methods=['GET', 'POST'])
@login_required
def r_course(course_name):
    completions = None  # Initialize completions to None
    if request.method == 'POST':
        completions = generate_text(course_name)
        rendered = render_template('courses/course1.html', completions=completions, course_name=course_name)
        new_course = Course(course_name=course_name, content=rendered, user_id=current_user.id)
        db.session.add(new_course)
        db.session.commit()
        return rendered
    # If the request method is 'GET', generate the text for the course
    completions = generate_text(course_name)
    return render_template('courses/course1.html', completions=completions, course_name=course_name)


@app.route('/saved_course/<course_name>')
@login_required
def saved_course(course_name):
    course = Course.query.filter_by(course_name=course_name, user_id=current_user.id).first()
    if course is None:
        # If there is no course with the given name, redirect to the home page
        return "<p>Course not found</p>"
    else:
        # If a course with the given name exists, render a template and pass the course to it
        return render_template('courses/saved_course.html', course=course)




@app.route('/module/<course_name>/<module_name>', methods=['GET'])
def module(course_name,module_name):
    content = generate_module_content(course_name,module_name)
    ic(content)
    if not content:
        return "<p>Module not found</p>"
    html = render_template('module.html', content=content)
    
    # If the 'download' query parameter is present in the URL, return the page as a PDF
    if 'download' in request.args:
        #Create a CSS object for the A3 page size
        a3_css = CSS(string='@page {size: A3; margin: 1cm;}')
        return render_pdf(HTML(string=html), stylesheets=[a3_css])

    # Otherwise, return the page as HTML
    return html 


@app.route('/app1')
def app1():
    if current_user.is_authenticated:
        saved_courses = Course.query.filter_by(user_id=current_user.id).all()
        recommended_courses = generate_recommendations(saved_courses)
        return render_template('app.html', saved_courses=saved_courses, recommended_courses = recommended_courses, user=current_user)
    else:
        return redirect(url_for('login'))


def markdown_to_list(markdown_string):
    # Split the string into lines
    lines = markdown_string.split('\n')
    # Use a regular expression to match lines that start with '* '
    list_items = [re.sub(r'\* ', '', line) for line in lines if line.startswith('* ')]
    return list_items



def generate_text(course):
    prompts = {
    'approach': f"You are a pedagogy expert and you are designing a learning material for {course} for an undergrad university student. You have to decide the approach to take for learning from this learning material. Please provide a brief description of the approach you would take to study this learning material (provide in points). After that, please provide a brief description of the learning outcomes that you expect from this learning material.",
    'modules': f"Based on the course {course}, please provide a list of modules that you would include in the course. Each module should be a subtopic of the course and should be listed in bullet points. Additionally, please provide a brief description of each module to give an overview of the content covered in the module.",
    }
    completions = {}

    for key, prompt in prompts.items():
        response = model.generate_content(prompt)
        print("Answer: ", response)

        if key == 'modules':
            if response.parts[0].text:
                print(markdown_to_list(response.parts[0].text))
                completions[key] = markdown_to_list(response.parts[0].text)
        else:
            completions[key] = markdown.markdown(response.parts[0].text) if response.parts[0].text else ""

    # for key, prompt in prompts.items():
    #     completion = model.generate_content(
    #         model=model,
    #         prompt=prompt,
    #         temperature=0.1,
    #         max_output_tokens=5000,
    #     )
    #     # Convert the markdown string to a list
    #     if key == 'modules':
    #         # Replace bullet points with asterisks
    #         markdown_string = completion.result.replace('•', '*') if completion.result else ""
    #         completions[key] = markdown_to_list(markdown_string) if markdown_string else []
    #     else:
    #         completions[key] = markdown.markdown(completion.result) if completion.result else ""
    ic(completions)
    return completions




def generate_module_content(course_name,module_name):
    # First prompt for module content
    module_prompt = f"Course Name: {course_name} Topic: {module_name}. Please provide a comprehensive explanation of {module_name}. Feel free to use examples or analogies to clarify complex ideas. Additionally, if there are specific aspects or questions you'd like to address within the topic, please mention them for a more focused response."

    module_completion = model.generate_content(module_prompt)
    if module_completion.parts:
        module_content = module_completion.parts[0].text if module_completion.parts[0].text else ""
    else:
        module_content = ""
    # Second prompt for code snippets
    code_prompt = f"Course Name: {course_name} Topic: {module_name}. If the explanation of {module_name} requires code snippets for better understanding, please provide the relevant code snippets."
    code_completion = model.generate_content(code_prompt)
    if code_completion.parts:
        code_content = code_completion.parts[0].text if code_completion.parts[0].text else ""
    else:
        code_content = ""
    # Second prompt for ASCII art
    ascii_prompt = f"Course Name: {course_name} Topic: {module_name}. If the explanation of {module_name} requires diagram snippets for better understanding, please provide the relevant diagram snippets in the form of ASCII art."
    ascii_completion  = model.generate_content(ascii_prompt)
    if ascii_completion.parts:
        ascii_content = ascii_completion.parts[0].text if ascii_completion.parts[0].text else ""
    else:
        ascii_content = ""
    # Convert the markdown string to HTML, wrapping code snippets with <pre><code> tags
    module_content_html = md.convert(module_content)
    code_content_html = md.convert(code_content)
    ascii_content_html = md.convert(ascii_content)

    # Combine the module content and code snippets
    combined_content = f"{module_content_html}\n{code_content_html}\n{ascii_content_html}"

    return  combined_content

def generate_recommendations(saved_courses):
    recommended_courses = []
    for course in saved_courses:
        prompt = f"Based on the course {course.course_name}, please provide just a single course name at the top and a description for new recommended course that would be beneficial for the student to take next. The description should be concise and informative (less than 70 characters)."
        response= model.generate_content(prompt)
        print("New Course Name: ", response)

        if response.parts[0].text:
            course_description = markdown.markdown(response.parts[0].text)
            recommended_courses.append({'name': course.course_name, 'description': course_description})

    return recommended_courses


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", debug=True)
