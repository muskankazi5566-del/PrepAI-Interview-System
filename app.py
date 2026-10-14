
import os
import random
import mysql.connector

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")


# ---------------------------------
# 1. CONNECT TO MYSQL DATABASE
# ---------------------------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "ai_interview_prep")
    )


# ---------------------------------
# 2. ADD SAMPLE INTERVIEW QUESTIONS
# ---------------------------------
def init_db():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM questions")
    count = cursor.fetchone()[0]

    if count == 0:
        sample_questions = [
            (
                "Data Analyst",
                "What is the difference between SQL and Python?",
                "SQL is used to store, retrieve and manage data in relational databases. Python is a programming language used for data analysis, automation, machine learning and general-purpose programming.",
                "SQL, database, Python, data analysis"
            ),
            (
                "Data Scientist",
                "What is machine learning?",
                "Machine learning is a branch of artificial intelligence that enables computers to learn patterns from data and make predictions or decisions without being explicitly programmed for every task.",
                "machine learning, artificial intelligence, data, patterns, prediction"
            ),
            (
                "Python Developer",
                "What are the main features of Python?",
                "Python is a high-level, interpreted and general-purpose programming language. It has simple syntax, supports multiple programming paradigms and provides many libraries.",
                "Python, high-level, interpreted, syntax, libraries"
            ),
            (
                "AI/ML Engineer",
                "What is the difference between AI, ML and deep learning?",
                "Artificial intelligence is the broad field of building systems that perform intelligent tasks. Machine learning is a subset of AI that learns from data. Deep learning is a subset of machine learning that uses neural networks with multiple layers.",
                "AI, machine learning, deep learning, neural networks, data"
            )
        ]

        cursor.executemany(
            """
            INSERT INTO questions (role, question, sample_answer, keywords)
            VALUES (%s, %s, %s, %s)
            """,
            sample_questions
        )
        connection.commit()

    cursor.close()
    connection.close()



# ---------------------------------
# 3. EVALUATE THE USER'S ANSWER
# ---------------------------------
def evaluate_answer(user_answer, sample_answer, keywords):
    user_answer = user_answer.strip()

    if not user_answer:
        return 0, "Please write an answer before submitting."

    # Compare the answer with the sample answer using TF-IDF
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(
        [user_answer, sample_answer]
    )
    similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]

    # Calculate keyword coverage
    keyword_list = [
        word.strip().lower()
        for word in (keywords or "").split(",")
        if word.strip()
    ]

    answer_lower = user_answer.lower()

    if keyword_list:
        matched = sum(
            1 for word in keyword_list if word in answer_lower
        )
        keyword_score = matched / len(keyword_list)
    else:
        keyword_score = 0

    # Combine similarity and keyword coverage
    score = round(
        (similarity * 70 + keyword_score * 30)
    )
    score = max(0, min(100, score))

    if score >= 75:
        feedback = "Good answer! You covered many important concepts."
    elif score >= 45:
        feedback = (
            "Fair answer. Add more relevant concepts and explain "
            "them with an example."
        )
    else:
        feedback = (
            "Keep practising. Review the topic and include more "
            "important concepts in your answer."
        )

    return score, feedback  



# ---------------------------------
# 4. HOME PAGE
# ---------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------
# 5. USER REGISTRATION
# ---------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register.html")

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name, email, generate_password_hash(password))
            )
            connection.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        except mysql.connector.IntegrityError:
            flash("This email is already registered.", "error")

        finally:
            cursor.close()
            connection.close()

    return render_template("register.html")


# ---------------------------------
# 6. USER LOGIN
# ---------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# ---------------------------------
# 7. USER LOGOUT
# ---------------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------
# 8. DASHBOARD
# ---------------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM questions")
    total_questions = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COUNT(*) AS total, AVG(score) AS average_score
        FROM interview_history
        WHERE user_id = %s
        """,
        (session["user_id"],)
    )
    stats = cursor.fetchone()

    cursor.execute(
        """
        SELECT h.score, h.created_at, q.role, q.question
        FROM interview_history h
        JOIN questions q ON h.question_id = q.id
        WHERE h.user_id = %s
        ORDER BY h.id DESC
        LIMIT 5
        """,
        (session["user_id"],)
    )
    recent_history = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        total_questions=total_questions,
        total_attempts=stats["total"],
        average_score=round(stats["average_score"] or 0, 1),
        recent_history=recent_history
    )


# ---------------------------------
# 9. START AN INTERVIEW
# ---------------------------------
@app.route("/interview", methods=["GET", "POST"])
def interview():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT DISTINCT role FROM questions ORDER BY role")
    roles = [row["role"] for row in cursor.fetchall()]

    selected_role = request.values.get("role", "").strip()

    if selected_role:
        cursor.execute(
            "SELECT * FROM questions WHERE role = %s",
            (selected_role,)
        )
    else:
        cursor.execute("SELECT * FROM questions")

    questions = cursor.fetchall()

    cursor.close()
    connection.close()

    if not questions:
        flash("No questions found. Please add questions to the database.", "error")
        return redirect(url_for("dashboard"))

    question = random.choice(questions)

    return render_template(
        "interview.html",
        question=question,
        roles=roles,
        selected_role=selected_role
    )


# ---------------------------------
# 10. SUBMIT AND EVALUATE ANSWER
# ---------------------------------
@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    if "user_id" not in session:
        return redirect(url_for("login"))

    question_id = request.form.get("question_id", type=int)
    user_answer = request.form.get("answer", "").strip()

    if not question_id:
        flash("Invalid question. Please try again.", "error")
        return redirect(url_for("interview"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM questions WHERE id = %s",
        (question_id,)
    )
    question = cursor.fetchone()

    if not question:
        cursor.close()
        connection.close()
        flash("Question not found.", "error")
        return redirect(url_for("interview"))

    score, feedback = evaluate_answer(
        user_answer,
        question["sample_answer"],
        question["keywords"]
    )

    cursor.execute(
        """
        INSERT INTO interview_history
        (user_id, question_id, user_answer, score, feedback)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            session["user_id"],
            question_id,
            user_answer,
            score,
            feedback
        )
    )
    connection.commit()

    cursor.close()
    connection.close()

    return render_template(
        "result.html",
        question=question,
        user_answer=user_answer,
        score=score,
        feedback=feedback,
        sample_answer=question["sample_answer"]
    )


# ---------------------------------
# 11. INTERVIEW HISTORY
# ---------------------------------
@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT h.id, h.user_answer, h.score, h.feedback,
               h.created_at, q.role, q.question
        FROM interview_history h
        JOIN questions q ON h.question_id = q.id
        WHERE h.user_id = %s
        ORDER BY h.id DESC
        """,
        (session["user_id"],)
    )
    records = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("history.html", records=records)



@app.route("/roles")
def roles_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT DISTINCT role FROM questions ORDER BY role"
    )
    roles = [row["role"] for row in cursor.fetchall()]

    cursor.close()
    connection.close()

    return render_template("role.html", roles=roles)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

    

