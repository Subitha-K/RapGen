from flask import Flask, render_template, request, send_file, session
from flask_bootstrap import Bootstrap
import spacy
import random
import io
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for session
Bootstrap(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Load English NLP model
nlp = spacy.load("en_core_web_sm")

def clean_text(text):
    """Remove or replace problematic characters for PDF output."""
    replacements = {
        "■": "",
        "“": "\"",
        "”": "\"",
        "’": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def generate_mcqs(text, num_questions=5):
    if not text:
        return []

    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]

    num_questions = min(num_questions, len(sentences))
    selected_sentences = random.sample(sentences, num_questions)

    mcqs = []
    for sentence in selected_sentences:
        sent_doc = nlp(sentence)
        candidates = [token.text for token in sent_doc if token.pos_ in ["NOUN", "PROPN"]]

        if not candidates:
            continue

        keyword = random.choice(candidates)
        question_stem = sentence.replace(keyword, "______", 1)

        distractors = list(set(candidates) - {keyword})
        while len(distractors) < 3:
            distractors.append("[Distractor]")

        distractors = random.sample(distractors, 3)
        options = [keyword] + distractors
        random.shuffle(options)

        correct_answer = chr(65 + options.index(keyword))
        mcqs.append((question_stem, options, correct_answer))

    return mcqs

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        text = ""
        if 'files[]' in request.files:
            files = request.files.getlist('files[]')
            for file in files:
                if file.filename.endswith('.pdf'):
                    text += process_pdf(file)
                elif file.filename.endswith('.txt'):
                    text += file.read().decode('utf-8')
        else:
            text = request.form['text']

        num_questions = int(request.form['num_questions'])
        mcqs = generate_mcqs(text, num_questions=num_questions)

        # Store MCQs in session so export can use them
        session['mcqs'] = mcqs

        mcqs_with_index = [(i + 1, mcq) for i, mcq in enumerate(mcqs)]
        return render_template('mcqs.html', mcqs=mcqs_with_index)

    return render_template('index.html')

@app.route('/export-pdf')
def export_pdf():
    mcqs = session.get('mcqs', [])
    if not mcqs:
        return "No MCQs to export! Please generate some first."

    buffer = io.BytesIO()

    # Create PDF doc
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=60, bottomMargin=40)

    # Styles (use built-in Helvetica, no TTF needed)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Question", fontName="Helvetica", fontSize=12, leading=15, spaceAfter=10))
    styles.add(ParagraphStyle(name="Option", fontName="Helvetica", fontSize=11, leftIndent=20, leading=13))
    styles.add(ParagraphStyle(name="Answer", fontName="Helvetica", fontSize=11, textColor="green", spaceAfter=15, leftIndent=20))

    content = []

    # Title
    content.append(Paragraph("<b>Generated MCQs</b>", styles["Title"]))
    content.append(Spacer(1, 20))

    # Add questions
    for idx, (question, options, correct) in enumerate(mcqs, 1):
        question = clean_text(question)

        # Question
        content.append(Paragraph(f"Q{idx}: {question}", styles["Question"]))

        # Options
        for i, option in enumerate(options):
            option = clean_text(option)
            content.append(Paragraph(f"{chr(65+i)}. {option}", styles["Option"]))

        # Correct Answer
        content.append(Paragraph(f"✔ Correct Answer: {correct}", styles["Answer"]))

    # Build PDF
    doc.build(content)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name="GeneratedQuestion.pdf",
                     mimetype="application/pdf")

def process_pdf(file):
    text = ""
    pdf_reader = PdfReader(file)
    for page_num in range(len(pdf_reader.pages)):
        page_text = pdf_reader.pages[page_num].extract_text()
        text += page_text
    return text

if __name__ == "__main__":
    app.run()
